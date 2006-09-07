#
# Copyright (c) 2005 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
import itertools

from conary import callbacks
from conary import errors
from conary import versions
from conary import conaryclient
from conary.conaryclient import ConaryClient, cmdline
from conary.build.cook import signAbsoluteChangeset
from conary.conarycfg import selectSignatureKey
from conary.deps import deps

def displayCloneJob(cs):
    indent = '   '
    for csTrove in cs.iterNewTroveList():
        newInfo = str(csTrove.getNewVersion())
        flavor = csTrove.getNewFlavor()
        if not flavor.isEmpty():
            newInfo += '[%s]' % flavor

        print "%sClone  %-20s (%s)" % (indent, csTrove.getName(), newInfo)

def CloneTrove(cfg, targetBranch, troveSpecList, updateBuildInfo = True,
               info = False, cloneSources = False, message = None, 
               test = False, fullRecurse = False):
    client = ConaryClient(cfg)
    repos = client.getRepos()

    targetBranch = versions.VersionFromString(targetBranch)
    if not isinstance(targetBranch, versions.Branch):
        raise errors.ParseError('Cannot specify full version "%s" to clone to - must specify target branch' % targetBranch)

    troveSpecs = [ cmdline.parseTroveSpec(x) for x in troveSpecList]

    componentSpecs = [ x[0] for x in troveSpecs 
                       if ':' in x[0] and x[0].split(':')[1] != 'source']
    if componentSpecs:
        raise errors.ParseError('Cannot clone components: %s' % ', '.join(componentSpecs))


    trovesToClone = repos.findTroves(cfg.installLabelPath, 
                                    troveSpecs, cfg.flavor)
    trovesToClone = list(set(itertools.chain(*trovesToClone.itervalues())))

    if not client.cfg.quiet:
        callback = conaryclient.callbacks.CloneCallback(client.cfg, message)
    else:
        callback = callbacks.CloneCallback()

    okay, cs = client.createCloneChangeSet(targetBranch, trovesToClone,
                                           updateBuildInfo=updateBuildInfo,
                                           infoOnly=info, callback=callback,
                                           fullRecurse=fullRecurse,
                                           cloneSources=cloneSources)
    if not okay:
        return

    if cfg.interactive or info:
        print 'The following clones will be created:'
        displayCloneJob(cs)

    labelConflicts = client._checkChangeSetForLabelConflicts(cs)
    if labelConflicts:
        print
        print 'WARNING: performing this clone will create label conflicts:'
        for troveTups in labelConflicts:
            print
            print '%s=%s[%s]' % (troveTups[0])
            print '  conflicts with %s=%s[%s]' % (troveTups[1])

        if not cfg.interactive and not info:
            print
            print 'error: interactive mode is required for when creating label conflicts'
            return

    if info:
        return

    if cfg.interactive:
        print
        okay = cmdline.askYn('continue with clone? [y/N]', default=False)
        if not okay:
            return

    sigKey = selectSignatureKey(cfg, str(targetBranch.label()))
    signAbsoluteChangeset(cs, sigKey)

    if not test:
        client.repos.commitChangeSet(cs, callback=callback)
