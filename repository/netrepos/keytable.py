#
# Copyright (c) 2004-2005 rPath, Inc.
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

import StringIO

import sqlite3
from lib import openpgpfile, openpgpkey

class OpenPGPKeyTable:
    def __init__(self, db):
        self.db = db
        cu = db.cursor()
        cu.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")
        tables = [ x[0] for x in cu ]
        if "PGPKeys" not in tables:
            cu.execute("""CREATE TABLE PGPKeys(keyId INTEGER,
                                               userId INTEGER,
                                               fingerprint STRING(40) UNIQUE,
                                               pgpKey BINARY,
                                               PRIMARY KEY(keyId))""")
        if "PGPFingerprints" not in tables:
            cu.execute("""CREATE TABLE PGPFingerprints(
                                             keyId INTEGER,
                                             fingerprint STRING(40),
                                             PRIMARY KEY(fingerprint))""")
        db.commit()

        # set the global key cache to refer to the keys in the database
        keyCache = OpenPGPKeyDBCache(self)
        openpgpkey.setKeyCache(keyCache)

    def getFingerprint(self, keyId):
        cu = self.db.cursor()
        r = cu.execute('SELECT fingerprint FROM PGPFingerprints '
                       'WHERE fingerprint LIKE "%' + keyId + '%"')
        keyList = r.fetchall()
        if (len(keyList) != 1):
            raise openpgpkey.KeyNotFound(keyId)
        return keyList[0][0]

    def addNewAsciiKey(self, userId, asciiData):
        keyData = openpgpfile.parseAsciiArmorKey(asciiData)
        if not keyData:
            raise IncompatibleKey('Unable to parse ASCII armored key')
        self.addNewKey(userId, keyData)

    def addNewKey(self, userId, pgpKeyData):
        cu = self.db.cursor()
        # start a transaction so that our SELECT is protected against
        # race conditions
        self.db._begin()
        r = cu.execute('SELECT IFNULL(MAX(keyId),0) + 1 FROM PGPKeys')
        keyId = r.fetchone()[0]
        keyRing = StringIO.StringIO(pgpKeyData)

        # make sure it's a public key
        keyType = openpgpfile.getBlockType(keyRing)
        keyRing.seek(-1,1)
        if (keyType >> 2) & 15 != openpgpfile.PKT_TAG_PUBLIC_KEY:
            raise IncompatibleKey('Key must be a public key')

        if openpgpfile.countKeys(keyRing) != 1:
            raise IncompatibleKey('Submit only one key at a time.')

        mainFingerprint = openpgpfile.getKeyId(keyRing)
        try:
            cu.execute('INSERT INTO PGPKeys VALUES(?, ?, ?, ?)',
                       (keyId, userId, mainFingerprint, pgpKeyData))
        except sqlite3.ProgrammingError:
            # potentially a duplicate fingerprint
            # FIXME: make a new error for this
            raise
        keyFingerprints = openpgpfile.getFingerprints(keyRing)
        for fingerprint in keyFingerprints:
            cu.execute('INSERT INTO PGPFingerprints VALUES(?, ?)',
                       (keyId, fingerprint))
        self.db.commit()
        keyRing.close()

    def deleteKey(self, keyId):
        fingerprint = self.getFingerprint(keyId)
        cu = self.db.cursor()
        cu.execute('SELECT keyId FROM PGPFingerprints '
                       'WHERE fingerprint=?', (fingerprint,))
        keyIds = cu.fetchall()
        if (len(keyIds) != 1):
            raise openpgpkey.KeyNotFound(keyId)
        keyId = keyIds[0]
        cu.execute('DELETE FROM PGPFingerprints WHERE keyId=?', (keyId,))
        cu.execute('DELETE FROM PGPKeys WHERE keyId=?', (keyId,))
        self.db.commit()

    def getPGPKeyData(self, keyId):
        cu = self.db.cursor()
        cu.execute("""SELECT pgpKey FROM PGPKeys
                           LEFT JOIN PGPFingerprints ON
                             PGPKeys.keyId=PGPFingerprints.keyId
                        WHERE PGPFingerprints.fingerprint like "%%%s%%"
                        """ %keyId)
        keys = cu.fetchall()
        if (len(keys) != 1):
            raise openpgpkey.KeyNotFound(keyId)
        return keys[0][0]

    def getUsersMainKeys(self, userId):
        cu = self.db.cursor()
        r = cu.execute('SELECT fingerprint FROM PGPKeys '
                       'WHERE userId=?', (userId,))
        return [ x[0] for x in r.fetchall() ]

    def getSubkeys(self, fingerprint):
        cu = self.db.cursor()
        r = cu.execute("""
                SELECT PGPFingerprints.fingerprint
                    FROM PGPFingerprints LEFT JOIN PGPKeys USING(keyid)
                WHERE PGPKeys.fingerprint=?
                     AND PGPFingerprints.fingerprint != PGPKeys.fingerprint""",
                       (fingerprint,))
        return [ x[0] for x in r.fetchall() ]

class OpenPGPKeyDBCache(openpgpkey.OpenPGPKeyCache):
    def __init__(self, keyTable = None):
        openpgpkey.OpenPGPKeyCache.__init__(self)
        self.keyTable = keyTable

    def setKeyTable(self, keyTable):
        self.keyTable = keyTable

    def getPublicKey(self, keyId):
        if keyId in self.publicDict:
            return self.publicDict[keyId]

        if self.keyTable is None:
            raise KeyNotFound(keyId, "Can't open database")

        # get the key data from the database
        fingerprint = self.keyTable.getFingerprint(keyId)
        keyData = self.keyTable.getPGPKeyData(keyId)

        # instantiate the crypto key object from the raw key data
        cryptoKey = openpgpfile.getPublicKeyFromString(keyId, keyData)

        # populate the cache
        self.publicDict[keyId] = openpgpkey.OpenPGPKey(fingerprint, cryptoKey)
        return self.publicDict[keyId]

