#
# Copyright (c) 2004 Specifix, Inc.
# All rights reserved
#
import copy
import difflib
import helper
import log
import patch
import versions

"""
Packages are groups of files and other packages, which are included by
reference. By convention, "package" often refers to a package with
files but no other packages, while a "group" means a package with other
packages but no files. While this object allows any mix of file and
package inclusion, in practice srs doesn't allow it.

Groups are most often created automatically as part of cook to group
the packages from a recipe together. Groups can also be specified by
a file which contains package names, white space, and a version. If
the package name isn't fully qualified, it's assumed to be part of the
same repository the group file is from. The version can be either fully
qualified or a branch nickname, in which case if refers to the head of
the branch at the time the group file is added to a repository.

Group files are parsed into group objects, which resolve the package and
name as specified above; the original group file is preserved for future
modification. This also allows a group file to be checked out and back
in again, and have it updated with new head versions of it's components.
Some groups (notably ones derived from recipes) exist only in their
parsed forms; these groups cannot be checked in or out.

Group files can contain comment lines (which begin with #), and the first
two lines should read::

    name NAME
    version VERSION

Where the name is a simple package name (not fully qualified) and the
version is just a version.
"""

# this is the repository's idea of a package
class Package:

    def copy(self):
	return copy.deepcopy(self)

    def getName(self):
        return self.name
    
    def getVersion(self):
        return self.version
    
    def changeVersion(self, version):
        self.version = version

    def getGroupFile(self):
	return self.groupFile
    
    def setGroupFile(self, contents):
	self.groupFile = contents
    
    def addFile(self, fileId, path, version):
	self.idMap[fileId] = (path, version)

    # fileId is the only thing that must be here; the other fields could
    # be "-"
    def updateFile(self, fileId, path, version):
	(origPath, origVersion) = self.idMap[fileId]

	if not path:
	    path = origPath

	if not version:
	    version = origVersion
	    
	self.idMap[fileId] = (path, version)

    def removeFile(self, fileId):   
	del self.idMap[fileId]

    def fileList(self):
	l = []
	mapping = {}

	for (theId, (path, version)) in self.idMap.items():
	    mapping[path] = theId

        paths = mapping.keys()
        paths.sort()
        for path in paths:
	    fileId = mapping[path]
	    version = self.idMap[fileId][1]
	    l.append((fileId, path, version))

	return l

    def getFile(self, fileId):
	return self.idMap[fileId]

    def hasFile(self, fileId):
	return self.idMap.has_key(fileId)

    def addPackageVersion(self, name, version):
	"""
	Adds a single version of a package.

	@param name: name of the package
	@type name: str
	@param version: version of the package
	@type version: versions.Version
	"""
	if self.packages.has_key(name):
	    self.packages[name].append(version)
	else:
	    self.packages[name] = [ version ]

    def addPackage(self, name, versionList):
	"""
	Adds a set of versions for a package.

	@param name: name of the package
	@type name: str
	@param versionList: list of versions to add
	@type versionList: list of versions.Version
	"""
	self.packages[name] = versionList

    def getPackageList(self):
	"""
	Returns a list of (packageName, versionList) ordered pairs, listing
	all of the package in the group, along with their versions. 

	@rtype: list
	"""
	return self.packages.items()

    def formatString(self):
	"""
	Returns a string representing everything about this package, which
	can later be read by the PackageFromFile object. The format of
	the string is:

	<file count> <group count>
	FILEID1 PATH1 VERSION1
	FILEID2 PATH2 VERSION2
	.
	.
	.
	FILEIDN PATHN VERSIONN
	PACKAGE1 VERSION1
	PACKAGE2 VERSION2
	.
	.
	.
	PACKAGEN VERSIONN
	GROUP FILE

	Group file may be empty, in which case nothing follows the newline
	for the final file package entry.

	"""
	rc = "%d %d\n" % (len(self.idMap), len(self.packages))
	for (fileId, (path, version)) in self.idMap.items():
	    rc += ("%s %s %s\n" % (fileId, path, version.freeze()))

	for pkg in self.packages.keys():
	    rc += pkg + " " +  \
		   " ".join([v.asString() for v in self.packages[pkg]]) + \
		   "\n"

	if self.groupFile:
	    rc += "\n".join(self.groupFile) + "\n"

	return rc

    # returns a dictionary mapping a fileId to a (path, version, pkgName) tuple
    def applyChangeSet(self, pkgCS):
	"""
	Updates the package from the changes specified in a change set.
	Returns a dictionary, indexed by fileId, which gives the
	(path, version, packageName) for that file.

	@param pkgCS: change set
	@type pkgCS: PackageChangeSet
	@rtype: dict
	"""

	fileMap = {}

	diff = pkgCS.getGroupFileDiff()
	if diff:
	    if not self.groupFile:
		oldLines = ""
	    else:
		oldLines = self.groupFile

	    (newLines, failedHunks) = patch.patch(oldLines, diff)

	    if failedHunks:
		# this really should never happen.
		raise PatchError

	    self.setGroupFile(newLines)

	for (fileId, path, fileVersion) in pkgCS.getNewFileList():
	    self.addFile(fileId, path, fileVersion)
	    fileMap[fileId] = self.idMap[fileId] + (self.name, )

	for (fileId, path, fileVersion) in pkgCS.getChangedFileList():
	    self.updateFile(fileId, path, fileVersion)
	    # look up the path/version in self.idMap as the ones here
	    # could be None
	    fileMap[fileId] = self.idMap[fileId] + (self.name, )

	for fileId in pkgCS.getOldFileList():
	    self.removeFile(fileId)

	# merge the included packages
	for (name, list) in pkgCS.getChangedPackages():
	    for (oper, version) in list:
		if oper == '+':
		    self.addPackageVersion(name, version)
		elif oper == "-":
		    for i, ver in enumerate(self.packages[name]):
			if ver.equal(version): break
		    if i == len(self.packages[name]):
			# FIXME, this isn't the right thing to do
			raise IOError

		    del(self.packages[name][i])
		    if not self.packages[name]:
			del self.packages[name]

	return fileMap

    def diff(self, them, abstract = 0):
	"""
	Generates a change set between them (considered the old version) and
	this instance. We return the change set, a list of other package diffs
	which should be included for this change set to be complete, and a list
	of file change sets which need to be included.  The list of package
	changes is of the form (pkgName, oldVersion, newVersion).  If abstract
	is True, oldVersion is always None and abstract diffs can be used.
	Otherwise, abstract versions are not necessary, and oldVersion of None
	means the package is new. The list of file changes is a list of
	(fileId, oldVersion, newVersion, newPath) tuples, where newPath is the
	path to the file in this package.

	@param them: object to generate a change set from (may be None)
	@type them: Group
	@param abstract: tells if this is a new group or an abstract change
	when them is None
	@type abstract: boolean
	@rtype: (ChangeSetGroup, packageChangeList, fileChangeList)
	"""

	# logical xor would be nice here, but it's not part of python :-(
	assert(not them or (not self.groupFile and not them.groupFile) or
	       (self.groupFile and them.groupFile))

	# find all of the file ids which have been added, removed, and
	# stayed the same
	if them:
	    themMap = them.idMap
	    chgSet = PackageChangeSet(self.name, them.getVersion(),	
				      self.getVersion())
	else:
	    themMap = {}
	    chgSet = PackageChangeSet(self.name, None, self.getVersion(),
				      abstract = abstract)

	removedIds = []
	addedIds = []
	sameIds = {}
	filesNeeded = []

	allIds = self.idMap.keys() + themMap.keys()
	for id in allIds:
	    inSelf = self.idMap.has_key(id)
	    inThem = themMap.has_key(id)
	    if inSelf and inThem:
		sameIds[id] = None
	    elif inSelf:
		addedIds.append(id)
	    else:
		removedIds.append(id)

	for id in removedIds:
	    chgSet.oldFile(id)

	for id in addedIds:
	    (selfPath, selfVersion) = self.idMap[id]
	    filesNeeded.append((id, None, selfVersion, selfPath))
	    chgSet.newFile(id, selfPath, selfVersion)

	for id in sameIds.keys():
	    (selfPath, selfVersion) = self.idMap[id]
	    (themPath, themVersion) = themMap[id]

	    newPath = None
	    newVersion = None

	    if selfPath != themPath:
		newPath = selfPath

	    if not selfVersion.equal(themVersion):
		newVersion = selfVersion
		filesNeeded.append((id, themVersion, selfVersion, selfPath))

	    if newPath or newVersion:
		chgSet.changedFile(id, newPath, newVersion)

	# now handle the packages we include
	names = {}
	list = self.packages.keys()
	if them:
	    list += them.packages.keys()

	for name in list:
	    names[name] = 1

	added = {}
	removed = {}

	for name in names.keys():
	    if self.packages.has_key(name):
		ourVersions = self.packages[name]
	    else:
		ourVersions = []

	    if them and them.packages.has_key(name):
		theirVersions = them.packages[name]
	    else:
		theirVersions = []

	    for (i, version) in enumerate(ourVersions):
		match = 0 
		for (j, v) in enumerate(theirVersions):
		    if v.equal(version):
			match = 1
			break

		if match:
		    # same version exists in both groups
		    del theirVersions[j]
		else:
		    # this is a new package
		    chgSet.newPackageVersion(name, version)
		    if (added.has_key(name)):
			added[name].append(version)
		    else:
			added[name] = [ version ]

	    for version in theirVersions:
		chgSet.oldPackageVersion(name, version)
		if (removed.has_key(name)):
		    removed[name].append(version)
		else:
		    removed[name] = [ version ]

	# create the diff of the groupFile if both versions have them. note
	# the assert above makes this test correct
	if self.groupFile:
	    if them:
		oldLines = them.groupFile
	    else:
		oldLines = ""
	    newLines = self.groupFile
	    diff = difflib.unified_diff(oldLines, newLines, "old", "new",
					lineterm = "")

	    # using try/except seems dumb, but I don't know any other
	    # way
	    try:
		diff.next()
		diff.next()
	    except StopIteration:
		pass

	    chgSet.setGroupFileDiff(diff)

	pkgList = []

	if abstract:
	    for name in added.keys():
		for version in added[name]:
		    pkgList.append((name, None, version))
	    return (chgSet, filesNeeded, pkgList)

	# use added and removed to assemble a list of package diffs which need
	# to go along with this change set
	for name in added.keys():
	    if not removed.has_key(name):
		for version in added[name]:
		    pkgList.append((name, None, version))
		continue

	    # name was changed between this version. for each new version
	    # of a package, try and generate the diff between that package
	    # and the version of the package which was removed which was
	    # on the same branch. if that's not possible, see if the parent
	    # of the package was removed, and use that as the diff. if
	    # we can't do that and only one version of this package is
	    # being obsoleted, use that for the diff. if we can't do that
	    # either, throw up our hands in a fit of pique
	    
	    for version in added[name]:
		branch = version.branch()
		if version.hasParent():
		    parent = version.parent()
		else:
		    parent = None
		found = 0

		if len(removed[name]) == 1:
		    pkgList.append((name, removed[name][0], version))
		else:
		    sameBranch = None
		    parentNode = None

		    for other in removed[name]:
			if other.branch().equal(branch):
			    sameBranch = other
			if parent and other.equal(parent):
			    parentNode = other

		    if sameBranch:
			pkgList.append((name, sameBranch, version))
		    elif parentNode:
			pkgList.append((name, parentNode, version))
		    else:
			# Here's the fit of pique. This shouldn't happen
			# except for the most ill-formed of groups.
			raise IOError, "ick. yuck. blech. ptooey."

	return (chgSet, filesNeeded, pkgList)

    def __init__(self, name, version):
	self.idMap = {}
	self.name = name
	self.version = version
	self.packages = {}
	self.groupFile = None

class PackageChangeSet:

    """
    Represents the changes between two packages and forms part of a
    ChangeSet. 
    """

    def isAbstract(self):
	return self.abstract

    def newFile(self, fileId, path, version):
	self.newFiles.append((fileId, path, version))

    def getNewFileList(self):
	return self.newFiles

    def oldFile(self, fileId):
	self.oldFiles.append(fileId)

    def getOldFileList(self):
	return self.oldFiles

    def getName(self):
	return self.name

    def changeOldVersion(self, version):
	self.oldVersion = version

    def changeNewVersion(self, version):
	self.newVersion = version

    def getOldVersion(self):
	return self.oldVersion

    def getNewVersion(self):
	return self.newVersion

    # path and/or version can be None
    def changedFile(self, fileId, path, version):
	self.changedFiles.append((fileId, path, version))

    def getChangedFileList(self):
	return self.changedFiles

    def getChangedPackages(self):
	return self.packages.items()

    def newPackageVersion(self, name, version):
	"""
	Adds a version of a package which appeared in newVersion.

	@param name: name of the package
	@type name: str
	@param version: new version
	@type version: versions.Version
	"""

	if not self.packages.has_key(name):
	    self.packages[name] = []
	self.packages[name].append(('+', version))

    def oldPackageVersion(self, name, version):
	"""
	Adds a version of a package which appeared in oldVersion.

	@param name: name of the package
	@type name: str
	@param version: old version
	@type version: versions.Version
	"""
	if not self.packages.has_key(name):
	    self.packages[name] = []
	self.packages[name].append(('-', version))

    def setGroupFileDiff(self, diff):
	self.groupFileDiff = diff

    def getGroupFileDiff(self):
	return self.groupFileDiff

    def parse(self, line):
	action = line[0]

	if action == "+" or action == "~":
	    (fileId, path, version) = line[1:].split()

	    if version == "-":
		version = None
	    else:
		version = versions.ThawVersion(version)

	    if path == "-":
		path = None

	    if action == "+":
		self.newFile(fileId, path, version)
	    else:
		self.changedFile(fileId, path, version)
	elif action == "-":
	    self.oldFile(line[1:])
	elif action == "p":
	    fields = line[2:].split()
	    name = fields[0]
	    verList = []
	    for item in fields[1:]:
		op = item[0]
		v = versions.ThawVersion(item[1:])

		assert(op == "+" or op == "-")

		if op == "+":
		    self.newPackageVersion(name, v)
		else: # op == "-"
		    self.oldPackageVersion(name, v)


    def formatToFile(self, changeSet, cfg, f):
	f.write("%s " % self.name)

	if self.isAbstract():
	    f.write("abstract ")
	elif self.oldVersion:
	    f.write("from %s to " % self.oldVersion.asString(cfg.defaultbranch))
	else:
	    f.write("new ")

	f.write("%s\n" % self.newVersion.asString(cfg.defaultbranch))

	for (fileId, path, version) in self.newFiles:
	    f.write("\tadded %s (%s(.*)%s)\n" % (path, fileId[:6], fileId[-6:]))

	for (fileId, path, version) in self.changedFiles:
	    if path:
		f.write("\tchanged %s (%s(.*)%s)\n" % 
			(path, fileId[:6], fileId[-6:]))
	    else:
		f.write("\tchanged %s\n" % fileId)
	    change = changeSet.getFileChange(fileId)
	    print "\t\t%s" % change

	for fileId in self.oldFiles:
	    f.write("\tremoved %s(.*)%s\n" % (fileId[:6], fileId[-6:]))

	for name in self.packages.keys():
	    list = [ x[0] + x[1].asString(cfg.defaultbranch) for x in self.packages[name] ]
	    f.write("\t" + stripNamespace(cfg.packagenamespace, name) + " " + " ".join(list) + "\n")

    def remapSinglePath(self, path, map, dict):
	# the first item in map remaps source packages, which are present
	# without a leading /
	newPath = path

	if path[0] != "/":
	    shortName = self.name.split(':')[-2]
	    prefix = map[0][1] % dict
	    newPath = prefix + path
	else:
	    for (prefix, newPrefix) in map[1:]:
		if path.startswith(prefix):
		    newPath = newPrefix + path[len(prefix):]

	return newPath

    def remapPaths(self, map, dict):
	for list in ( self.changedFiles, self.newFiles ):
	    for i in range(0,len(list)):
		if list[i][1]:
		    newPath = self.remapSinglePath(list[i][1], map, dict)
		    if newPath != list[i][1]:
			list[i] = (list[i][0], newPath, list[i][2])

    def freeze(self):
	"""
	Returns a string representation of this change set which can
	later be parsed by parse(). The representation begins with a
	header::

         SRS PKG ABSTRACT <name> <newversion> <linecount> <diffcount>
         SRS PKG CHANGESET <name> <oldversion> <newversion> <linecount> <diffcount>
         SRS PKG NEW <name> <newversion> <linecount> <diffcount>

	It is followed by <linecount> lines, each of which specifies a
	new file, old file, removed file, or a change to the set of
	included packages. Each of these lines begins with a "+", "-",
	"~", or "p" respectively. Following that are <diffcount> (possibly
	0) lines which make up the diff for the group file.

	@rtype: string
	"""

	rc = ""
	lines = 0

	for id in self.getOldFileList():
	    rc += "-%s\n" % id

	for (id, path, version) in self.getNewFileList():
	    rc += "+%s %s %s\n" % (id, path, version.freeze())

	for (id, path, version) in self.getChangedFileList():
	    rc += "~%s " % id
	    if path:
		rc += path
	    else:
		rc += "-"

	    if version:
		rc += " " + version.freeze() + "\n"
	    else:
		rc += " -\n"

	lines = []
	for name in self.packages.keys():
	    list = [ x[0] + x[1].freeze() for x in self.packages[name] ]
	    lines.append("p " + name + " " + " ".join(list))

	if lines:
	    rc += "\n".join(lines) + "\n"

	mainLineCount = rc.count("\n")

	if self.groupFileDiff:
	    groupLineCount = 0
	    for diff in self.groupFileDiff:
		groupLineCount += 1
		rc += diff + "\n"
	else:
	    groupLineCount = 0

	if self.abstract:
	    hdr = "SRS PKG ABSTRACT %s %s %d %d\n" % \
		      (self.name, self.newVersion.freeze(), mainLineCount,
		       groupLineCount)
	elif not self.oldVersion:
	    hdr = "SRS PKG NEW %s %s %d %d\n" % \
		      (self.name, self.newVersion.freeze(), mainLineCount,
		       groupLineCount)
	else:
	    hdr = "SRS PKG CHANGESET %s %s %s %d %d\n" % \
		      (self.name, self.oldVersion.freeze(), 
		       self.newVersion.freeze(), mainLineCount, groupLineCount)

	return hdr + rc

    def __init__(self, name, oldVersion, newVersion, abstract = 0):
	self.name = name
	self.oldVersion = oldVersion
	self.newVersion = newVersion
	self.newFiles = []
	self.oldFiles = []
	self.changedFiles = []
	self.abstract = abstract
	self.packages = {}
	self.groupFileDiff = None

class PackageFromFile(Package):

    def read(self, dataFile):
	lines = dataFile.readlines()

	fields = lines[0].split()
	fileCount = int(fields[0])
	pkgCount = int(fields[1])

	start = 1
	fileEnd = start + fileCount
	pkgEnd = fileEnd + pkgCount

	for line in lines[start:fileEnd]:
	    (fileId, path, version) = line.split()
	    version = versions.ThawVersion(version)
	    self.addFile(fileId, path, version)

	for line in lines[fileEnd:pkgEnd]:
	    items = line.split()
	    name = items[0]
	    self.packages[name] = []
	    for versionStr in items[1:]:
		version = versions.VersionFromString(versionStr)
		self.addPackageVersion(name, version)

	# this strips the newlines off the end
	groupFileList = [ x[:-1] for x in lines[pkgEnd:] ]
	self.setGroupFile(groupFileList)

    def __init__(self, name, dataFile, version):
	"""
	Initializes a PackageFromFile() object.

	@param name: Fully qualified name of the package 
	@type name: str
	@param dataFile: File representation of a package
	@type dataFile: file-type object
	@param version: Fully qualified version of the package
	@type version: versions.Version()
	"""

	Package.__init__(self, name, version)
	self.read(dataFile)

class GroupFromTextFile(Package):

    def getSimpleVersion(self):
	"""
	Returns the version string defined in a group file.

	@rtype: str
	"""
	return self.simpleVersion

    def parseFile(self, f, packageNamespace, repos):
	"""
	Parses a group file into a group object. Any existing contents
	of the group object are erased. Any errors which occur are
	logged, and if the file has not been parsed properly False is
	return; if parsing is successful the simple version number from
	the group file is returned as a string.
	
	@param f: The file to be parsed
	@type f: file-like object
	@param packageNamespace: The name of the repository to prepend
	to package names which are not fully qualified; this should begin
	with a colon.
	@type packageNamespace: str
	@param repos: Branch nicknames are turned into fully qualified
	version numbers by looking them up in repos.
	@type repos: Repository
	@rtype: str
	"""
	self.groupFile = f.read().split("\n")
	# cut off the empty string added at the end due to the trailing
	# newline
	del self.groupFile[-1]

	lines = []
	errors = 0
	for i, line in enumerate(self.groupFile):
	    line = line.strip()
	    if line and line[0] != '#': 
		fields = line.split()
		if len(fields) != 2:
		    log.error("line %d of group file has too many fields" % i)
		    errors = 1
		lines.append((i, fields))

	if lines[0][1][0] != "name":
	    log.error("group files must contain the group name on the first line")
	    errors = 1
	    name = "localhost:unknown"
	else:
	    name = lines[0][1][1]
	    if name[0] != ":":
		name = packageNamespace + ":" + name
	    else:
		name = name

	    if name.count(":") != 2:
		log.error("group names may not include colons")
		errors = 1
		name = "localhost:unknown"

	    last = name.split(":")[-1]
	    if not last.startswith("group-"):
		log.error('group names must start with "group-"')
		errors = 1

	self.name = name

	if lines[1][1][0] != "version":
	    log.error("group files must contain the version on the first line")
	    errors = 1
	else:
	    self.simpleVersion = lines[1][1][1]

	for lineNum, (name, versionStr) in lines[2:]:
	    try:
		pkgList = helper.findPackage(repos, packageNamespace,
					 None, name, versionStr)
	    except helper.PackageNotFound, e:
		log.error("error parsing group file line %d: %s" 
			    % (lineNum, str(e)))
		errors = 1
		continue

	    versionList = [ x.getVersion() for x in pkgList ]
	    self.addPackage(pkgList[0].getName(), versionList)

	if errors:
	    raise ParseError

    def __init__(self, f, packageNamespace, repos):
	"""
	Initializes the object; parameters are the same as those
	to parseFile().
	"""

	Package.__init__(self, None, None)
	self.parseFile(f, packageNamespace, repos)

def stripNamespace(namespace, pkgName):
    if pkgName.startswith(namespace + ":"):
	return pkgName[len(namespace) + 1:]
    return pkgName

class PackageError(Exception):

    """
    Ancestor for all exceptions raised by the package module.
    """

    pass

class ParseError(PackageError):

    """
    Indicates that an error occured parsing a group file.
    """

    pass

class PatchError(PackageError):

    """
    Indicates that an error occured parsing a group file.
    """

    pass

