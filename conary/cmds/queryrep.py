#
# Copyright (c) 2004-2008 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
Provides the output for the "conary repquery" command
"""
import itertools

from conary import conaryclient, files, trove
from conary.conaryclient import cmdline
from conary import display
from conary.deps import deps
from conary.cmds import cscmd
from conary.repository import trovesource, errors
from conary.lib import log
from conary.errors import ConaryError

VERSION_FILTER_ALL    = 0
VERSION_FILTER_LATEST = 1
VERSION_FILTER_LEAVES = 2

FLAVOR_FILTER_ALL    = 0
FLAVOR_FILTER_AVAIL  = 1
FLAVOR_FILTER_BEST   = 2
FLAVOR_FILTER_EXACT  = 3


def displayTroves(cfg, troveSpecs=[], pathList = [], whatProvidesList=[],
                  # query options
                  versionFilter=VERSION_FILTER_LATEST,
                  flavorFilter=FLAVOR_FILTER_BEST,
                  useAffinity = False,
                  # trove options
                  info = False, digSigs = False, showDeps = False,
                  showBuildReqs = False, showBuildLog = False, filesToShow = [],
                  # file options
                  ls = False, lsl = False, ids = False, sha1s = False,
                  tags = False, fileDeps = False, fileVersions = False,
                  fileFlavors = False, capsules = False,
                  # collection options
                  showTroves = False, recurse = None, showAllTroves = False,
                  weakRefs = False, showTroveFlags = False,
                  alwaysDisplayHeaders = False,
                  troveTypes=trovesource.TROVE_QUERY_PRESENT):
    """
       Displays information about troves found in repositories

       @param cfg: conary config
       @type cfg: conarycfg.ConaryConfiguration
       @param troveSpecs: troves to search for
       @type troveSpecs: list of troveSpecs (n[=v][[f]])
       @param versionFilter: add documentation here.  Check man page for
       general description
       @type versionFilter: bool
       @param flavorFilter: add documentation here.  Check man page for
       general description.
       @type flavorFilter: bool
       @param useAffinity: If False, disallow affinity database use.
       @type useAffinity: bool
       @param info: If true, display general information about the trove
       @type info: bool
       @param digSigs: If true, display digital signatures for a trove.
       @type digSigs: bool
       @param showBuildReqs: If true, display the versions and flavors of the
       build requirements that were used to build the given troves
       @type showBuildReqs: bool
       @param showDeps: If true, display provides and requires information
       for the trove.
       @type showDeps: bool
       @param ls: If true, list files in the trove
       @type ls: bool
       @param lsl: If true, list files in the trove + ls -l information
       @type lsl: bool
       @param ids: If true, list pathIds for files in the troves
       @type ids: bool
       @param sha1s: If true, list sha1s for files in the troves
       @type sha1s: bool
       @param tags: If true, list tags for files in the troves
       @type tags: bool
       @param fileDeps: If true, print file-level dependencies
       @type fileDeps: bool
       @param fileVersions: If true, print fileversions
       @type fileVersions: bool
       @param showTroves: If true, display byDefault True child troves of this
       trove
       @type showTroves: bool
       @param recurse: display child troves of this trove, recursively
       @type recurse: bool
       @param showAllTroves: If true, display all byDefault False child troves
       of this trove
       @type showAllTroves: bool
       @param weakRefs: display both weak and strong references of this trove.
       @type weakRefs: bool
       @param showTroveFlags: display [<flags>] list with information about
       the given troves.
       @type showTroveFlags: bool
       @param alwaysDisplayHeaders: If true, display headers even when listing
       files.
       @type alwaysDisplayHeaders: bool
       @rtype: None
    """

    if showBuildLog and len(troveSpecs)>1:
        raise ConaryError('Error: can not show build log for several packages. Please specify one')
    if filesToShow and len(troveSpecs)>1:
        raise ConaryError('Error: can not show files log for several packages. Please specify one')

    client = conaryclient.ConaryClient(cfg)
    repos = client.getRepos()

    if useAffinity:
        affinityDb = client.db
    else:
        affinityDb = None

    whatProvidesList = [ deps.parseDep(x) for x in whatProvidesList ]

    troveTups = getTrovesToDisplay(repos, troveSpecs, pathList,
                                   whatProvidesList,
                                   versionFilter, flavorFilter,
                                   cfg.installLabelPath, cfg.flavor,
                                   affinityDb,
                                   troveTypes=troveTypes)

    if (filesToShow or showBuildLog) and len(troveTups)>1:
        raise ConaryError('Error: %s is ambigious. Please specify one of: \n%s' % \
                    (troveSpecs[0],
                    "\n".join([x[0]+"="+str(x[1].trailingLabel()) for x in troveTups]) ))

    dcfg = display.DisplayConfig(repos, affinityDb)

    dcfg.setTroveDisplay(deps=showDeps, info=info,
                         showBuildReqs=showBuildReqs, showBuildLog=showBuildLog, filesToShow = filesToShow,
                         digSigs=digSigs, fullVersions=cfg.fullVersions,
                         showLabels=cfg.showLabels, fullFlavors=cfg.fullFlavors,
                         showComponents = cfg.showComponents,
                         baseFlavors = cfg.flavor)

    dcfg.setFileDisplay(ls=ls, lsl=lsl, ids=ids, sha1s=sha1s, tags=tags,
                        fileDeps=fileDeps, fileVersions=fileVersions,
                        fileFlavors=fileFlavors, capsules=capsules)

    recurseOne = showTroves or showAllTroves or weakRefs
    if recurse is None and not recurseOne and troveSpecs:
        # if we didn't explicitly set recurse and we're not recursing one
        # level explicitly and we specified troves (so everything won't
        # show up at the top level anyway), guess at whether to recurse
        recurse = True in (ls, lsl, ids, sha1s, tags, showDeps, fileDeps,
                           fileVersions, fileFlavors)
    displayHeaders = alwaysDisplayHeaders or showTroveFlags

    dcfg.setChildDisplay(recurseAll = recurse, recurseOne = recurseOne,
                         showNotByDefault = showAllTroves or showBuildLog,
                         showWeakRefs = weakRefs,
                         showTroveFlags = showTroveFlags,
                         displayHeaders = displayHeaders,
                         checkExists = False)

    if troveSpecs:
        dcfg.setPrimaryTroves(set(troveTups))


    formatter = display.TroveFormatter(dcfg)

    display.displayTroves(dcfg, formatter, troveTups)


def getTrovesToDisplay(repos, troveSpecs, pathList, whatProvidesList,
                       versionFilter, flavorFilter, labelPath, defaultFlavor,
                       affinityDb, troveTypes=trovesource.TROVE_QUERY_PRESENT):
    """ Finds troves that match the given trove specifiers, using the
        current configuration, and parameters

        @param repos: a network repository client
        @type repos: repository.netclient.NetworkRepositoryClient
        @param troveSpecs: troves to search for
        @type troveSpecs: list of troveSpecs (n[=v][[f]])
        @param versionFilter: The VERSION_FILTER_* to use.  See man
        page for documentation for now.
        @param flavorFilter: The FLAVOR_FILTER_* to use.  See man
        page for documentation for now.
        @param labelPath: The labelPath to search
        @type labelPath: list
        @param defaultFlavor: The default flavor(s) to search with
        @type defaultFlavor: list
        @param affinityDb: The affinity database to search with.
        @type affinityDb: bool

        @rtype: troveTupleList (list of (name, version, flavor) tuples)
    """
    def _merge(resultD, response):
        for troveName, troveVersions in response.iteritems():
            d = resultD.setdefault(troveName, {})
            for version, flavors in troveVersions.iteritems():
                d.setdefault(version, []).extend(flavors)
        return resultD

    troveTups = []
    if troveSpecs or pathList or whatProvidesList:
        if whatProvidesList:
            tupList = []
            for label in labelPath:
                sols = repos.resolveDependencies(label, whatProvidesList)
                for solListList in sols.itervalues():
                    # list of list of solutions to the depSet
                    tupList.extend(itertools.chain(*solListList))

            source = trovesource.SimpleTroveSource(tupList)
            source.searchAsRepository()

            troveNames = set(x[0] for x in tupList)
            results = getTrovesToDisplay(source, troveNames, [], [],
                                         versionFilter, flavorFilter, labelPath,
                                         defaultFlavor, affinityDb=None,
                                         troveTypes=troveTypes)
            troveTups.extend(results)

        # Search for troves using findTroves.  The options we
        # specify to findTroves are determined by the version and
        # flavor filter.
        if pathList:
            troveTups += getTrovesByPath(repos, pathList, versionFilter,
                                         flavorFilter, labelPath, defaultFlavor)


        if not troveSpecs:
            return sorted(troveTups, display._sortTroves)

        # Search for troves using findTroves.  The options we
        # specify to findTroves are determined by the version and
        # flavor filter.
        troveSpecs = [ ((not isinstance(x, str) and x) or
                         cmdline.parseTroveSpec(x, allowEmptyName=False)) \
                                                        for x in troveSpecs ]
        searchFlavor = defaultFlavor

        acrossLabels = True
        if versionFilter == VERSION_FILTER_ALL:
            getLeaves = False
        elif versionFilter == VERSION_FILTER_LATEST:
            # we just want to limit all searches for the very latest
            # version node.  Find trove makes this difficult, we
            # do the leaves search and then filter.
            getLeaves = True
            acrossLabels = False
        elif versionFilter == VERSION_FILTER_LEAVES:
            # This will return all versions that are 'leaves', that is,
            # are the latest with a unique flavor string.
            getLeaves = True
            acrossLabels = False
        else:
            assert(0)

        exactFlavors = False
        if flavorFilter == FLAVOR_FILTER_ALL:
            searchFlavor = None
            bestFlavor = False
            acrossFlavors = True # there are no flavors to go 'across'
            newSpecs = []
            origSpecs = {}
            # We do extra processing here.  We want FLAVOR_FILTER_ALL to work
            # when you specify a flavor to limit the all to.
            # But findTrove won't let us do that, since it expects that
            # the flavors it gets passed are supersets of the trove flavors
            # So we search with no flavor and search by hand afterwards.
            for (n, vS, fS) in troveSpecs:
                origSpecs.setdefault((n, vS), []).append(fS)
                newSpecs.append((n, vS, None))
            troveSpecs = newSpecs
            affinityDb = None
        elif flavorFilter == FLAVOR_FILTER_AVAIL:
            # match install flavor + maybe affinity, could affect rq branch,
            # return all flavors that match.
            bestFlavor = False
            acrossFlavors = True
            if versionFilter != VERSION_FILTER_ALL:
                getLeaves = True
        elif flavorFilter == FLAVOR_FILTER_BEST:
            # match install flavor + affinity, could affect rq branch,
            # return best match.
            bestFlavor = True
            acrossFlavors = False
        elif flavorFilter == FLAVOR_FILTER_EXACT:
            exactFlavors = True
            acrossFlavors = False
            bestFlavor = False

        if not affinityDb:
            acrossLabels = True

        results = repos.findTroves(labelPath,
                                   troveSpecs, searchFlavor,
                                   affinityDatabase = affinityDb,
                                   acrossLabels = acrossLabels,
                                   acrossFlavors = acrossFlavors,
                                   allowMissing = False,
                                   bestFlavor = bestFlavor,
                                   getLeaves = getLeaves,
                                   troveTypes = troveTypes,
                                   exactFlavors = exactFlavors)

        # do post processing on the result if necessary
        if (flavorFilter == FLAVOR_FILTER_ALL
            or versionFilter == VERSION_FILTER_LATEST):
            for (n,vS,fS), tups in results.iteritems():
                if not tups:
                    continue
                if versionFilter == VERSION_FILTER_LATEST:
                    # only look at latest leaves (1 per branch).
                    versionsByBranch = {}
                    for tup in tups:
                        versionsByBranch.setdefault(tup[1].branch(),
                                                    []).append(tup[1])
                    maxVersions = set(max(x) for x in versionsByBranch.values())
                    tups = [ x for x in tups if x[1] in maxVersions ]
                for (_, v, f) in tups:
                    if flavorFilter == FLAVOR_FILTER_ALL:
                        # only look at latest leaf.
                        foundMatch = False
                        for fS in origSpecs[n, vS]:
                            # FIXME: switch to stronglySatisfies
                            # in order to implement primary flavor support
                            # here at least?
                            if (fS is None) or f.satisfies(fS):
                                foundMatch = True
                                break
                        if not foundMatch:
                            continue
                    troveTups.append((n, v, f))
        else:
            troveTups.extend(itertools.chain(*results.itervalues()))
    else:
        if flavorFilter == FLAVOR_FILTER_EXACT:
            flavorFilter = FLAVOR_FILTER_BEST

        # no troves specified, use generic fns with no names given.
        if versionFilter == VERSION_FILTER_ALL:
            queryFn = repos.getTroveVersionsByLabel
        elif versionFilter == VERSION_FILTER_LATEST:
            queryFn = repos.getTroveLatestByLabel
        elif versionFilter == VERSION_FILTER_LEAVES:
            queryFn = repos.getTroveLatestByLabel


        if flavorFilter == FLAVOR_FILTER_ALL:
            flavor = None
            bestFlavor = False
            affinityDb = None
        elif flavorFilter == FLAVOR_FILTER_AVAIL:
            # match affinity flavors
            # must be done client side...
            flavor = None
            bestFlavor = False
            affinityDb = None # for now turn off
        elif flavorFilter == FLAVOR_FILTER_BEST:
            # match affinity flavors
            # must be done client side...
            flavor = None
            bestFlavor = False
            affinityDb = None # XXX for now turn off.

        resultsDict = {}

        resultsDict = queryFn({'': {labelPath[0] : flavor}},
                               bestFlavor = bestFlavor, troveTypes=troveTypes)
        for label in labelPath[1:]:
            d = queryFn({'': {label : flavor}}, bestFlavor = bestFlavor,
                        troveTypes=troveTypes)
            _merge(resultsDict, d)

        # do post processing for VERSION_FILTER_LATEST, FLAVOR_FILTER_BEST,
        # and FLAVOR_FILTER_AVAIL
        troveTups = []
        for name, versionDict in resultsDict.iteritems():
            if affinityDb:
                localFlavors = [x[2] for x in affinityDb.trovesByName(name)]
            else:
                localFlavors = []

            versionsByLabel = {}
            for version, flavorList in versionDict.iteritems():
                versionsByLabel.setdefault(version.trailingLabel(),
                                            []).append((version, flavorList))


            for versionDict in versionsByLabel.itervalues():
                for version, flavorList in sorted(versionDict, reverse=True):
                    if flavorFilter == FLAVOR_FILTER_BEST:
                        best = None
                        for systemFlavor in defaultFlavor:
                            matchScores = []
                            if localFlavors:
                                matchFlavors = [ deps.overrideFlavor(systemFlavor, x) for x in localFlavors]
                            else:
                                matchFlavors = [systemFlavor]

                            for f in flavorList:
                                scores = ( (x.score(f), f) for x in matchFlavors)
                                scores = [ x for x in scores if x[0] is not False]
                                if scores:
                                    matchScores.append(max(scores))
                            if matchScores:
                                best = max(matchScores)[1]
                                break
                        if best is not None:
                            flavorList = [best]
                        else:
                            continue
                    elif flavorFilter == FLAVOR_FILTER_AVAIL:
                        if localFlavors:
                            matchFlavors = []
                            for systemFlavor in defaultFlavor:
                                matchFlavors.extend(deps.overrideFlavor(systemFlavor, x) for x in localFlavors)
                        else:
                            matchFlavors = defaultFlavor
                    added = False
                    for flavor in flavorList:
                        if flavorFilter == FLAVOR_FILTER_AVAIL:
                            found = False
                            for matchFlavor in matchFlavors:
                                if matchFlavor.satisfies(flavor):
                                    found = True
                                    break
                            if not found:
                                continue
                        troveTups.append((name, version, flavor))
                        added = True
                    if added and versionFilter == VERSION_FILTER_LATEST:
                        break
    return sorted(troveTups, display._sortTroves)


def getTrovesByPath(repos, pathList, versionFilter, flavorFilter, labelPath,
                    defaultFlavor):
    if not pathList:
        return []

    if versionFilter == VERSION_FILTER_ALL:
        queryFn = repos.getTroveVersionsByPath
    elif versionFilter == VERSION_FILTER_LEAVES:
        queryFn = repos.getTroveLeavesByPath
    elif versionFilter == VERSION_FILTER_LATEST:
        queryFn = repos.getTroveLeavesByPath
    else:
        assert(0)

    allResults = {}
    for label in labelPath:
        try:
            results = queryFn(pathList, label)
        except errors.MethodNotSupported:
            log.debug('repository server for the %s label does not support '
                      'queries by path' %label)
            continue
        for path, tups in results.iteritems():
            allResults.setdefault(path, []).extend(tups)

    allResults = [ allResults.get(x) for x in pathList ]

    finalList = [ ]
    for tupList in allResults:
        if not tupList:
            continue
        source = trovesource.SimpleTroveSource(tupList)
        source.searchAsRepository()
        troveNames = set(x[0] for x in tupList)
        # no affinity when searching by path.
        results = getTrovesToDisplay(source, troveNames, [], [],
                                     versionFilter, flavorFilter, labelPath,
                                     defaultFlavor, None)
        finalList.extend(results)
    return finalList

def diffTroves(cfg, troveSpec, withTroveDeps = False, withFileTags = False,
               withFileVersions = False, withFileDeps = False,
               withFileContents = False, showLabels = False,
               fullVersions = False, fullFlavors = False,
               showEmptyDiffs = False, withBuildReqs = False,
               withFiles = False, withFilesStat = False):
    client = conaryclient.ConaryClient(cfg)
    # Fetch the absolute changeset for the old trove and the relative
    # changeset from the old trove to the new trove
    primaryCsList = cscmd.computeTroveList(client, [ troveSpec ])
    trv = primaryCsList[0]
    if trv[1] == trv[2]:
        # Diffing against ourselves
        print "Identical troves"
        return
    primaryCsList = [ (trv[0], (None, None), trv[1], True), trv ]
    cs = client.createChangeSet(primaryCsList, withFiles=True,
                                withFileContents=False)
    oldTroves = {}
    newTroves = {}
    newTroveCsList = []
    for trvCs in cs.iterNewTroveList():
        trvName = trvCs.getName()
        if trvCs.getOldVersion() is None:
            flavor = trvCs.getNewFlavor()
            if trvCs.isAbsolute():
                # isAbsolute() can be False, and getOldVersion() returns None
                # if it's a new trove
                oldTroves[(trvName, flavor)] = trove.Trove(trvCs)
            newTroves[(trvName, flavor)] = trove.Trove(trvCs)
        else:
            newTroveCsList.append(trvCs)

    for trvCs in newTroveCsList:
        trv = newTroves[(trvCs.getName(), trvCs.getOldFlavor())]
        trv.applyChangeSet(trvCs)

    del newTroveCsList

    sOldTroves = set(oldTroves)
    sNewTroves = set(newTroves)
    # trvAdded and trvRemoved are ignored here, we'll catch changes at the
    # toplevel compornent level anyway
    #trvAdded = sNewTroves.difference(sOldTroves)
    #trvRemoved = sOldTroves.difference(sNewTroves)
    trvChanged = sNewTroves.intersection(sOldTroves)

    trvDepsKeys = DiffDisplay.troveDependencyLabels

    diffs = {}
    # Check dependencies
    for trvName, trvFlavor in trvChanged:
        trvDiff = {}
        oldTrv = oldTroves[(trvName, trvFlavor)]
        newTrv = newTroves[(trvName, trvFlavor)]

        trvDiff.update(_diffTroveCollections(oldTrv, newTrv))
        trvDiff.update(_diffTroveFlavors(oldTrv, newTrv))
        trvDiff.update(_diffTroveDeps(oldTrv, newTrv, trvDepsKeys))
        trvDiff.update(_diffBuildRequirements(oldTrv, newTrv))
        # XXX Metadata

        trvDiff.update(_diffFiles(cs, oldTrv, newTrv))

        if showEmptyDiffs or trvDiff:
            diffs[(trvName, trvFlavor)] = trvDiff

    diffDisplay = DiffDisplay(oldTroves, newTroves, diffs,
                              fullFlavors = fullFlavors,
                              fullVersions = fullVersions,
                              showLabels = showLabels,
                              showEmptyDiffs = showEmptyDiffs,
                              withBuildReqs = withBuildReqs,
                              withFileContents = withFileContents,
                              withFileDeps = withFileDeps,
                              withFilesStat = withFilesStat,
                              withFiles = withFiles,
                              withFileTags = withFileTags,
                              withFileVersions = withFileVersions,
                              withTroveDeps = withTroveDeps,
                              )
    for line in diffDisplay.lines():
        print line

class DiffDisplay(object):
    charOld = '-'
    charNew = '+'
    charRemoved = '-'
    charAdded = '+'

    pads = [ " " * 2 * i for i in range(6) ]

    troveDependencyLabels = [('Provides', 'getProvides'), ('Requires', 'getRequires')]

    def __init__(self, oldTroves, newTroves, diffs, **kwargs):
        self.fullFlavors = kwargs.pop('fullFlavors')
        self.fullVersions = kwargs.pop('fullVersions')
        self.showLabels = kwargs.pop('showLabels')
        self.showEmptyDiffs = kwargs.pop('showEmptyDiffs')
        self.withBuildReqs = kwargs.pop('withBuildReqs')
        self.withFileContents = kwargs.pop('withFileContents')
        self.withFileDeps = kwargs.pop('withFileDeps')
        self.withFiles = kwargs.pop('withFiles')
        self.withFilesStat = kwargs.pop('withFilesStat')
        self.withFileTags = kwargs.pop('withFileTags')
        self.withFileVersions = kwargs.pop('withFileVersions')
        self.withTroveDeps = kwargs.pop('withTroveDeps')

        if self.withFilesStat or self.withFileTags or self.withFileDeps:
            self.withFiles = True

        self.oldTroves = oldTroves
        self.newTroves = newTroves
        self.diffs = diffs

    def lines(self):
        for (trvName, trvFlavor), trvDiff in sorted(self.diffs.iteritems()):
            if not trvDiff and not self.showEmptyDiffs:
                continue
            for line in self.formatDiffTrove(trvName, trvFlavor, trvDiff, padLevel=0):
                yield line

    def formatDiffTrove(self, trvName, trvFlavor, trvDiff, padLevel):
        padding = self.pads[padLevel]
        otrv = self.oldTroves[(trvName, trvFlavor)]
        ntrv = self.newTroves[(trvName, trvFlavor)]
        yield "%s%s %s=%s" % (padding, self.charOld, trvName,
            self.formatVF((otrv.getVersion(), otrv.getFlavor())))
        yield "%s%s %s=%s" % (padding, self.charNew, trvName,
            self.formatVF((ntrv.getVersion(), ntrv.getFlavor())))

        for line in self.formatDiffFlavor(trvDiff, padLevel + 1): yield line
        for line in self.formatDiffColl(trvDiff, padLevel + 1): yield line
        for line in self.formatTroveDeps(trvDiff, padLevel + 1): yield line
        for line in self.formatBuildReqs(trvDiff, padLevel + 1): yield line
        for line in self.formatFileList(trvDiff, padLevel + 1): yield line

    def formatDiffFlavor(self, trvDiff, padLevel):
        pad1 = self.pads[padLevel]
        pad2 = self.pads[padLevel + 1]
        if 'flavor' in trvDiff and not self.fullFlavors:
            o, n = trvDiff['flavor']
            yield "%sFlavors:" % pad1
            yield "%s%s %s" % (pad2, self.charOld, o)
            yield "%s%s %s" % (pad2, self.charNew, n)

    def formatDiffColl(self, trvDiff, padLevel):
        pad1 = self.pads[padLevel]
        pad2 = self.pads[padLevel + 1]
        if 'isCollection' in trvDiff:
            o, n = trvDiff['isCollection']
            yield "%s%s is a collection: %s" % (pad1, bool(o))
            yield "%s%s is a collection: %s" % (pad1, bool(n))

        if 'troveList' in trvDiff:
            added, removed = trvDiff['troveList']
            yield "%sTrove list:" % pad1
            template = "%s%s %s=%s"
            for n, v, f in removed:
                yield template % (pad2, self.charRemoved, n,
                                  self.formatVF((v,f)))
            for n, v, f in added:
                yield template % (pad2, self.charAdded, n,
                                  self.formatVF((v,f)))

    def formatTroveDeps(self, trvDiff, padLevel):
        if 'troveDeps' not in trvDiff:
            return
        pad1 = self.pads[padLevel]
        if not self.withTroveDeps:
            yield "%sDependencies" % (pad1, )
            return

        pad2 = self.pads[padLevel + 1]
        tDeps = trvDiff['troveDeps']
        for (dep, meth) in self.troveDependencyLabels:
            if dep not in tDeps:
                continue
            val = tDeps[dep]
            yield "%s%s:" % (pad1, dep)
            for sense, vdep in zip((self.charAdded, self.charRemoved), val):
                for v in self._iterDeps(vdep):
                    if not v:
                        continue
                    yield "%s%s %s" % (pad2, sense, v)

    def _iterDeps(self, thawDep):
        return sorted(str(thawDep).split('\n'))

    def formatBuildReqs(self, trvDiff, padLevel):
        if 'buildRequirements' not in trvDiff:
            return
        pad1 = self.pads[padLevel]
        if not self.withBuildReqs:
            yield "%sBuild Requirements" % (pad1, )
            return

        pad2 = self.pads[padLevel + 1]
        yield "%sBuild Requirements:" % pad1
        added, removed, changed = trvDiff['buildRequirements']
        template = "%s%s %s=%s"
        for n, (v, f) in sorted(removed):
            ostr = self.formatVF((v, f))
            yield template % (pad2, self.charRemoved, n, ostr)
        for n, (v, f) in sorted(added):
            ostr = self.formatVF((v, f))
            yield template % (pad2, self.charAdded, n, ostr)

        for n, (ov, of), (nv, nf) in sorted(changed):
            ostr = self.formatVF((ov, of))
            nstr = self.formatVF((nv, nf))
            yield template % (pad2, self.charRemoved, n, ostr)
            yield template % (pad2, self.charAdded, n, nstr)

    def formatFileList(self, trvDiff, padLevel):
        if 'fileDiffs' not in trvDiff:
            return
        pad1 = self.pads[padLevel]
        if not self.withFiles:
            yield "%sFiles" % (pad1, )
            return

        pad2 = self.pads[padLevel + 1]
        pad3 = self.pads[padLevel + 2]
        pad4 = self.pads[padLevel + 3]
        pad5 = self.pads[padLevel + 4]
        yield "%sFile Changes:" % pad1
        added, removed, changed = trvDiff['fileDiffs']
        if removed:
            yield "%sRemoved:" % pad2
            for n, (v, pid, fid) in sorted(removed):
                yield "%s%s" % (pad3, n)
        if added:
            yield "%sAdded:" % pad2
            for n, (v, pid, fid) in sorted(added):
                yield "%s%s" % (pad3, n)
        if changed:
            yield "%sChanged:" % pad2
            for item in sorted(changed):
                n, (ov, opid, ofid), (nv, npid, nfid) = item[:3]
                yield "%s%s" % (pad3, n)
                if self.withFileVersions:
                    template = "%s%s %s"
                    yield template % (pad4, "File versions:", "")
                    yield template % (pad4, self.charOld, ov)
                    yield template % (pad4, self.charNew, nv)

                # Inode diff present
                inodeO, inodeN = [], []
                statChanged = False
                for iO, iN in item[3][:-3]:
                    if iO == iN:
                        iN = ''
                    else:
                        statChanged = True
                    inodeO.append(iO)
                    inodeN.append(iN)

                (typO, permO, ownO, grpO, mtimeO, sizeO) = inodeO
                (typN, permN, ownN, grpN, mtimeN, sizeN) = inodeN
                # Fix up owner and group
                if ownO.startswith('+'):
                    ownO = ownO[1:]
                if ownN.startswith('+'):
                    ownN = ownN[1:]
                if grpO.startswith('+'):
                    grpO = grpO[1:]
                if grpN.startswith('+'):
                    grpN = grpN[1:]

                # Shorten the output for the regular case: no changes, regular
                # file
                if not typN and typO == "(RegularFile)":
                    typO = ""

                if statChanged and self.withFilesStat:
                    yield "%sFile details:" % (pad4, )
                    template = "%s%s %9s %-8s %-8s %8s %23s %s"
                    yield template % (pad4, self.charOld, permO, ownO, grpO,
                                      sizeO, mtimeO, typO)
                    yield template % (pad4, self.charNew, permN, ownN, grpN,
                                      sizeN, mtimeN, typN)
                elif statChanged:
                    yield "%sFile details" % (pad4, )

                tagO, tagN = item[3][6]

                addedProv, removedProv = item[3][7]
                addedReq, removedReq = item[3][7]

                map = [('Provides', addedProv, removedProv),
                       ('Requires', addedReq, removedReq)]

                template = "%s%s %s"
                senses = (self.charRemoved, self.charAdded)
                for title, addedDep, removedDep in map:
                    title = pad4 + title
                    if addedDep or removedDep:
                        if not self.withFileDeps:
                            yield title
                            continue
                        yield title + ':'
                        for sense, deps in zip(senses, (removedDep, addedDep)):
                            for v in self._iterDeps(deps):
                                yield template % (pad5, sense, v)

                if tagO == tagN:
                    continue
                if self.withFileTags:
                    yield "%sFile tags:" % (pad4, )
                    template = "%s%s %s"
                    yield template % (pad4, self.charOld, tagO)
                    yield template % (pad4, self.charNew, tagN)
                else:
                    yield "%sFile tags" % (pad4, )

    def formatVF(self, VF):
        """Formats the version-flavor tuple according to the display options"""
        return formatVF(VF, fullFlavors = self.fullFlavors,
                        showLabels = self.showLabels,
                        fullVersions = self.fullVersions)

def _diffTroveCollections(oldTrv, newTrv):
    oldIsColl = oldTrv.isCollection()
    newIsColl = newTrv.isCollection()
    ret = {}
    if not (oldIsColl or newIsColl):
        # Neither are collections
        return ret
    if (oldIsColl and newIsColl):
        ocoll = dict((x[0], x) for x in oldTrv.iterTroveList(strongRefs=True))
        ncoll = dict((x[0], x) for x in newTrv.iterTroveList(strongRefs=True))
        socoll = set(ocoll.keys())
        sncoll = set(ncoll.keys())
        if socoll != sncoll:
            added = sorted([ ncoll[x] for x in sncoll - socoll ])
            removed = sorted([ ocoll[x] for x in socoll - sncoll ])
            ret['troveList'] = (added, removed)
    else:
            # Format is (old, new)
        ret['isCollection'] = (oldIsColl, newIsColl)
    return ret

def _diffTroveFlavors(oldTrv, newTrv):
    # Flavor changed?
    ret = {}
    oldFlv, newFlv = oldTrv.getFlavor(), newTrv.getFlavor()
    if oldFlv != newFlv:
        ret['flavor'] = (oldFlv, newFlv)
    return ret

def _diffTroveDeps(oldTrv, newTrv, depKeys):
    ret = {}
    for (dep, meth) in depKeys:
        oldD = getattr(oldTrv, meth)()
        newD = getattr(newTrv, meth)()
        added, removed = newD - oldD, oldD - newD
        if added or removed:
            ret[dep] = (added, removed)
    if ret:
        return {'troveDeps' : ret}
    return ret

def _diffBuildRequirements(oldTrv, newTrv):
    oldBR = dict((x[0], (x[1], x[2])) for x in oldTrv.getBuildRequirements())
    newBR = dict((x[0], (x[1], x[2])) for x in newTrv.getBuildRequirements())
    ret = _diffNV(oldBR, newBR)
    if not ret:
        return {}
    return {'buildRequirements' : ret}

def _diffFiles(changeset, oldTrv, newTrv):
    oldFiles = dict((x[1], (x[3], x[0], x[2])) for x in oldTrv.iterFileList())
    newFiles = dict((x[1], (x[3], x[0], x[2])) for x in newTrv.iterFileList())
    ret = _diffNV(oldFiles, newFiles)
    if not ret:
        return {}
    added, removed, changed = ret
    if not changed:
        return {'fileDiffs' : ret}
    fchanged = []
    for (fPath, (fOldVer, fOldPId, fOldFId), (fNewVer, fNewPId, fNewFId)) in changed:
        if fOldFId == fNewFId:
            # Same file ID, so they are identical
            continue
        changeOld = changeset.getFileChange(None, fOldFId)
        changeNew = changeset.getFileChange(fOldFId, fNewFId)
        fObjOld = files.ThawFile(changeOld, fOldPId)
        if changeNew and files.fileStreamIsDiff(changeNew):
            fObjNew = files.ThawFile(changeOld, fOldPId)
            fObjNew.twm(changeNew, fObjOld)
        else:
            if changeNew is None:
                changeNew = changeset.getFileChange(None, fNewFId)
            if changeNew is None:
                raise Exception("Unable to retrieve file")
            fObjNew = files.ThawFile(changeNew, fNewFId)
        # Diff the inodes
        idiff = []
        idiff.append(("(%s)" % fObjOld.__class__.__name__,
                      "(%s)" % fObjNew.__class__.__name__))
        for acs in ['permsString', 'owner', 'group', 'timeString']:
            vold = getattr(fObjOld.inode, acs)()
            vnew = getattr(fObjNew.inode, acs)()
            idiff.append((vold, vnew))

        szold = fObjOld.sizeString()
        sznew = fObjNew.sizeString()
        idiff.append((szold.strip(), sznew.strip()))

        # tags
        idiff.append((' '.join(sorted(fObjOld.tags)),
                      ' '.join(sorted(fObjNew.tags))))

        oProv, nProv = fObjOld.provides(), fObjNew.provides()
        oReqs, nReqs = fObjOld.requires(), fObjNew.requires()

        idiff.append((nProv - oProv, oProv - nProv))
        idiff.append((nReqs - oReqs, oReqs - nReqs))

        # idiff is (type, perms, owner, group, time, size, tag, provides,
        # requires)
        fchanged.append((fPath, (fOldVer, fOldPId, fOldFId),
                                (fNewVer, fNewPId, fNewFId), tuple(idiff)))

    if not (added or removed or fchanged):
        # No change
        return {}
    return {'fileDiffs' : (added, removed, fchanged)}

def _diffNV(dict1, dict2):
    """
    Diffs two dictionaries of NV objects, keyed on N, with V as
    value
    Return a 3-item tuple: added, removed, changed
    Added and removed are NV lists
    changed is a list of (n, oldV, newV)
    """

    setN1 = set(dict1)
    setN2 = set(dict2)
    added, removed = setN2 - setN1, setN1 - setN2

    added = [ (x, dict2[x]) for x in added ]
    removed = [ (x, dict1[x]) for x in removed ]
    # Potentially changed
    common = setN1.intersection(setN2)
    # Extract the file versions
    # Put file versions in a dictionary keyed by path
    cLeft = dict((x, dict1[x]) for x in common)
    # Walk the other file versions and compare them with the old ones

    vDiffs = []
    for fPath, fValRight in ((x, dict2[x]) for x in common):
        fValLeft = cLeft[fPath]
        if fValLeft[0] == fValRight[0]:
            del cLeft[fPath]
        else:
            vDiffs.append((fPath, fValLeft, fValRight))

    if added or removed or vDiffs:
        return added, removed, vDiffs

    return None

def formatVF(vf, showLabels=False, fullVersions=False, fullFlavors=False):
    ver, flavor = _splitVF(vf)

    if not showLabels and not fullVersions:
        vdisp = ver.trailingRevision()
    elif fullVersions:
        vdisp = ver.asString()
    else: #labels
        vdisp = "%s/%s" % (ver.branch().label(), ver.trailingRevision())

    if not fullFlavors or flavor is None:
        return vdisp
    return "%s[%s]" % (vdisp, flavor)

def _splitVF(vf):
    if isinstance(vf, tuple):
        assert len(vf) == 2, "Expected 2-item tuple, got %s items" % len(vf)
        return vf
    return vf, None