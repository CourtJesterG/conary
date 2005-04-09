#
# Copyright (c) 2004-2005 Specifix, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any waranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
import metadata
import os
import sys

import kid
import templates 

from metadata import MDClass
from repository.netrepos import netserver

class ServerError(Exception):
    def __str__(self):
        return self.str
        
class InvalidServerCommand(ServerError):
    str = """Invalid command passed to server."""

class HttpHandler:
    def __init__(self, repos):
        self.repos = repos
        self.troveStore = repos.troveStore
        self.templatePath = os.path.dirname(sys.modules['templates'].__file__) + os.path.sep
        self.cfg = self.repos.cfg
       
        # "command name": (command handler, page title, 
        #       (requires auth, requires write access, requires admin))
        self.commands = {
             # metadata commands
             "":               (self.main, "Conary Repository",
                               (True, True, False)),
             "main":           (self.main, "Conary Repository",
                               (True, True, False)),
             "metadata":       (self.metadata, "View Metadata",          
                               (True, True, False)),
             "chooseBranch":   (self.chooseBranch, "View Metadata",
                               (True, True, False)),
             "getMetadata":    (self.getMetadata, "View Metadata",       
                               (True, True, False)),
             "updateMetadata": (self.updateMetadata, "Metadata Updated", 
                               (True, True, False)),
             
             # user administration commands
             "userlist":       (self.userlist, "User Administration",    
                               (True, False, True)),
             "addPermForm":    (self.addPermForm, "Add Permission",
                               (True, False, True)),
             "addPerm":        (self.addPerm, "Add Permission",
                               (True, False, True)),
             "deletePerm":     (self.deletePerm, "Delete Permission",
                               (True, False, True)),
             "addUserForm":    (self.addUserForm, "Add User",            
                               (True, False, True)),
             "addUser":        (self.addUser, "Add User",                
                               (True, False, True)),
             "addGroupForm":   (self.addGroupForm, "Add Group",
                               (True, False, True)),
             "addGroup":       (self.addGroup, "Add Group",
                               (True, False, True)),
             # change password commands
             "chPassForm":     (self.chPassForm, "Change Password",
                               (True, False, False)),
             "chPass":         (self.chPass, "Change Password",
                               (True, False, False)),
        }

    def requiresAuth(self, cmd):
        if cmd in self.commands:
            return self.commands[cmd][2][0]
        else:
            return True

    def handleCmd(self, writeFn, cmd, authToken=None, fields=None):
        """Handle either an HTTP POST or GET command."""
        self.writeFn = writeFn
        if cmd.endswith('/'):
            cmd = cmd[:-1]

        # handle the odd case of style sheet and javascript libraries
        # XXX these items are served with the wrong content-type
        if cmd in ["style.css", "library.js"]:
            f = open(os.path.join(self.templatePath, cmd))
            self.writeFn(f.read())
            f.close()
            return 
    
        if cmd in self.commands:
            handler = self.commands[cmd][0]
            pageTitle = self.commands[cmd][1]
        else:
            raise InvalidServerCommand

        needWrite = self.commands[cmd][2][1]
        needAdmin = self.commands[cmd][2][2]
        if not self.repos.auth.check(authToken, write=needWrite, admin=needAdmin):
            raise netserver.InsufficientPermission

        if cmd == "":
	    home = None
        else:
	    home = self.repos.urlBase

        self.pageTitle = pageTitle
        handler(authToken, fields)

    def kid_write(self, templateName, **values):
        path = os.path.join(self.templatePath, templateName + ".kid")
        t = kid.load_template(path)
        self.writeFn(t.serialize(encoding="utf-8", pageTitle=self.pageTitle, cfg = self.cfg, **values))

    def main(self, authToken, fields):
        self.kid_write("main_page", fields=fields)

    def metadata(self, authToken, fields, troveName=None):
        troveList = list(self.repos.troveStore.iterTroveNames())
        troveList.sort()

        # pick the next trove in the list
        # or stay on the previous trove if canceled
        if "troveName" in fields:
            troveName = fields["troveName"].value
        elif troveName in troveList:
            loc = troveList.index(troveName)
            if loc < len(troveList):
                troveName = troveList[loc+1]

        self.kid_write("pick_trove", troveList = troveList,
                                     troveName = troveName)

    def chooseBranch(self, authToken, fields):
        if fields.has_key('troveName'):
            troveName = fields['troveName'].value
        else:
            troveName = fields['troveNameList'].value
        
        source = str(fields.getfirst('source', '')).lower()
        
        versions = self.repos.getTroveVersionList(authToken,
            netserver.SERVER_VERSIONS[-1], { troveName : None })
        
        branches = {}
        for version in versions[troveName]:
            version = self.repos.thawVersion(version)
            branches[version.branch()] = True

        branches = branches.keys()
        if len(branches) == 1:
            self._getMetadata(fields, troveName, branches[0].freeze())
        else:
            self.kid_write("choose_branch",
                           branches = branches,
                           troveName = troveName,
                           source = source)

    def getMetadata(self, authToken, fields):
        troveName = fields['troveName'].value

        branch = fields['branch'].value
        self._getMetadata(fields, troveName, branch)

    def _getMetadata(self, fields, troveName, branch):
        branch = self.repos.thawVersion(branch)

        if "source" in fields and fields["source"].value.lower() == "freshmeat":
            if "freshmeatName" in fields:
                fmName = fields["freshmeatName"].value
            else:
                fmName = troveName[:-7]
            try:
                md = metadata.fetchFreshmeat(fmName)
            except metadata.NoFreshmeatRecord:
                self.kid_write("error", error = "No Freshmeat record found.")
                return
        else:
            md = self.troveStore.getMetadata(troveName, branch)

        if not md: # fill a stub
            md = metadata.Metadata(None)

        self.kid_write("metadata", metadata = md, branch = branch,
                                   troveName = troveName)

    def updateMetadata(self, authToken, fields):
        branch = self.repos.thawVersion(fields["branch"].value)
        troveName = fields["troveName"].value
        
        self.troveStore.updateMetadata(troveName, branch,
            fields["shortDesc"].value,
            fields["longDesc"].value,
            fields.getlist("selUrl"),
            fields.getlist("selLicense"),
            fields.getlist("selCategory"),
            fields["source"].value,
            "C"
        )

        self.metadata(authToken, fields, troveName)
        
    def userlist(self, authToken, fields):
        self.kid_write("user_admin", netAuth = self.repos.auth)

    def addPermForm(self, authToken, fields):
        groups = (x[1] for x in self.repos.auth.iterGroups())
        labels = (x[1] for x in self.repos.auth.iterLabels())
        troves = (x[1] for x in self.repos.auth.iterItems())
    
        self.kid_write("permission", groups=groups, labels=labels, troves=troves)

    def addPerm(self, authToken, fields):
        group = str(fields.getfirst("group", ""))
        label = str(fields.getfirst("label", ""))
        trove = str(fields.getfirst("trove", ""))

        write = bool(fields.getfirst("write", False))
        capped = bool(fields.getfirst("capped", False))
        admin = bool(fields.getfirst("admin", False))

        self.repos.auth.addAcl(group, trove, label,
                                   write, capped, admin)
        self.kid_write("notice", message = "Permission successfully added.",
                                 link = "User Administration",
                                 url = "userlist")
   
    def addGroupForm(self, authToken, fields):
        users = dict(self.repos.auth.iterUsers())
        self.kid_write("add_group", users = users)
   
    def addGroup(self, authToken, fields):
        groupName = fields["userGroupName"].value
        initialUserIds = fields.getlist("initialUserIds")

        newGroupId = self.repos.auth.addGroup(groupName)
        for userId in initialUserIds:
            self.repos.auth.addGroupMember(newGroupId, userId)

        self.kid_write("notice", message = "Group successfully created.",
                                 link = "User Administration",
                                 url = "userlist")
   
    def deletePerm(self, authToken, fields):
        groupId = str(fields.getfirst("groupId", ""))
        labelId = fields.getfirst("labelId", None)
        itemId = fields.getfirst("itemId", None)

        self.repos.auth.deletePermission(groupId, labelId, itemId)
        self.kid_write("notice", message = "Permission deleted.",
                                 link = "User Administration",
                                 url = "userlist")
   
    def addUserForm(self, authToken, fields):
        self.kid_write("add_user")

    def addUser(self, authToken, fields):
        user = fields["user"].value
        password = fields["password"].value
       
        if fields.has_key("write"):
            write = True
        else:
            write = False

        if fields.has_key("admin"):
            admin = True
        else:
            admin = False
        self.repos.addUser(authToken, 0, user, password)
        self.repos.addAcl(authToken, 0, user, "", "", write, True, admin)

        self.kid_write("notice", message = "User successfully added.",
                                 link = "User Administration",
                                 url = "userlist")
       
    def chPassForm(self, authToken, fields):
        if fields.has_key("username"):
            username = fields["username"].value
            askForOld = False
        else:
            username = authToken[0]
            askForOld = True
        
        self.kid_write("change_password", username = username, askForOld = askForOld)
        
    def chPass(self, authToken, fields):
        username = fields["username"].value
        admin = self.repos.auth.check(authToken, admin=True)
        
        if username != authToken[0]:
            if not admin:
                raise netserver.InsufficientPermission
        
        if fields.has_key("oldPassword"):
            oldPassword = fields["oldPassword"].value
        else:
            oldPassword = None
        p1 = fields["password1"].value
        p2 = fields["password2"].value

        if authToken[1] != oldPassword and authToken[0] == username and not admin:
            self.kid_write("error", error = "Error: old password is incorrect")
        elif p1 != p2:
            self.kid_write("error", error = "Error: passwords do not match")
        elif oldPassword == p1:
            self.kid_write("error", error = "Error: old and new passwords identical, not changing")
        else:
            self.repos.auth.changePassword(username, p1)
            if admin:
                returnLink = ("User Administration", "userlist")
            else:
                returnLink = ("Main Menu", "main")

            self.kid_write("notice", message = "Password successfully changed",
                                     link = returnLink[0], url = returnLink[1])                             
