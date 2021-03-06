Protocol Revisions
==================

Conary's internal XMLRPC API uses numbered revisions to negotiate which
protocol will be used for client-server communications.

Both clients and servers are expected to maintain system update functionality
with reasonable forward- and backwards-compatibility indefinitely, so that
clients can always update to the latest version.

Version 73:
  - Added 'resumeOffset' arg to getChangeSet
  - Added 'extra' dictionary to return value from getChangeset. extra may
    contain a 'resumeOffset' key indicating how many bytes were skipped in the
    response changeset. extra may contain a 'tag' key holding an opaque
    checksum of the changeset.

Version 72:
  - added getRoleFilters, setRoleFilters

Version 71:
  - corrected accidental use of X-Conary-UsedAnonymous as an error flag

Version 70:
  - added getDepsForTroveList, getTimestamps

Version 69:
  - added getCommitProgress
  - prepareChangeset() returns a tuple of url,
    supportsGetCommitProgress (because the call is not supported on
    standalone repositories)

Version 68:
  - added getFileContentsCapsuleInfo 

Version 67:
  - added getFileContentsFromTrove

Version 66:
  - added getLabelsForHost

Version 65:
  - getTroveInfo and getNewTroveInfo calls filter extended metadata from
    results for older clients

Version 64:
  - getTroveInfo call understands CLONEDFROMLIST troveInfo

Version 63:
  - added calls addRoleMember and getRoleMembers

Version 62:
  - added xmlrpc api call commitCheck()
  - getPackageBranchPathIds now passes on a list of dirnames instead of filePrefixes

Version 61:
  - The following methods have been renamed for consistency:
    addAccessGroup -> addRole
    addEntitlementGroup -> addEntitlementClass
    addEntitlementOwnerAcl -> addEntitlementClassOwner
    addEntitlements -> addEntitlementKeys
    deleteAccessGroup -> deleteRole
    deleteEntitlementGroup -> deleteEntitlementClass
    deleteEntitlementOwnerAcl -> deleteEntitlementClassOwner
    deleteEntitlements -> deleteEntitlementKeys
    getEntitlementClassAccessGroup -> getEntitlementClassesRoles
    getUserGroups -> getRoles
    listAccessGroups -> listRoles
    listEntitlementGroups -> listEntitlementClasses
    listEntitlements -> listEntitlementKeys
    setEntitlementClassAccessGroup -> setEntitlementClassesRoles
    setUserGroupCanMirror -> setRoleCanMirror
    setUserGroupIsAdmin -> setRoleIsAdmin
    updateAccessGroupMembers -> updateRoleMembers

Version 60:
  - server side support for setUserGroupIsAdmin
  - addAcl and editAcl cannot be used for setting the admin flag anymore
  - fixed keyword arguments to work through proxy
  - don't include useAnonymous in return values
  - return exception details as (exceptName, args, kwwargs) insteace of
    (exceptName,) + args

Version 51:
  - getChangeSet supports infoOnly parameter
  - parameters are passed as (args, kwArgs) instead of individually

Version 50:
  - getChangeSet keeps (troveNeeded, filesNeeded, troveRemoved) information
    separate for each element of the job list

Version 49:
  - added mirrorMode to getChangeSet and getFingerprints which forces files
    to be included in changesets whenever the changeset is across hosts

Version 48: Conary 1.1.25
  - Added extra argument to getChangeSet to force the creation of a specific
    changeset version.

Version 47:
  - Added getNewTroveInfo and setTroveInfo
  - added addMetadataItems call

Version 46:
  - Added hidden flag to commitChangeSet and hasTroves call (only allowed for
    users with mirror or write permissions, respectively) and the
    presentHiddenTroves() call which requires write permissions

Version 45:
  - addDigitalSignature takes a VersionedSignatureSet object. This call
    is incompatible between versions 43 and 44 of the protocol (though this
    could be addressed, to a limited extent).
  - indicates that the repository can store V1 signatures and unknown troveinfo

Version 44:
  - added support for decoding "chunked" Transfer-encoding requests
    from clients
  - added support for obtaining sizes of changesets > 2 GiB via the
    getChangeSet() and getFileContents() calls. The sizes are now
    returned as strings instead of ints.

Version 43:
  - added getTroveReferences call.
  - added getTroveDescendants call
  - switched to fileId,pathId indexed changesets (changeset 2007022001)
  - added getChangesetFingerprints call (not exposed in netclient)
  - getTroveInfo now advertises troves as missing instead of raising
    PermissionDenied

Version 42: Conary 1.1.17
 - Client uses negotiated protocol version
 - getFileContents has authOnly parameter


Version 41: Conary 1.1.16
 - Added getTroveInfo call [proxy requires at least this version]
