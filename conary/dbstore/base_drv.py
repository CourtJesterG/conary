#
# Copyright (c) 2005-2009 rPath, Inc.
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

import sys
import traceback
import re

import sqlerrors, sqllib


(DEBUG_OFF,
        DEBUG_WARN, # Print stack on invalid txn ops
        DEBUG_WARN_ALL, # Print stack on all txn ops
        DEBUG_ERROR, # Enter debugger on invalid txn ops
    ) = range(4)
DEBUG_TRANSACTIONS = DEBUG_OFF


# class for encapsulating binary strings for dumb drivers
class BaseBinary:
    def __init__(self, s):
        assert(isinstance(s, str))
        self.s = s
    def __str__(self):
        return self.s
    def __repr__(self):
        return self.s

# this will be derived by the backend drivers to handle schema creation
class BaseKeywordDict(dict):
    keys = { 'PRIMARYKEY'    : 'INTEGER PRIMARY KEY',
             'BLOB'          : 'BLOB',
             'MEDIUMBLOB'    : 'BLOB',
             'STRAIGHTJOIN'  : '',
             'TABLEOPTS'     : '',
             'PATHTYPE'      : 'STRING',
             'STRING'        : 'STRING',
             'CREATEVIEW'    : 'CREATE VIEW',
             'CHANGED'       : 'NUMERIC(14,0) NOT NULL DEFAULT 0',
             }
    def __init__(self):
        dict.__init__(self, self.keys)

    def binaryVal(self, binLen):
        return "BINARY(%d)" % binLen

    def __getitem__(self, val):
        if val.startswith('BINARY'):
            binLen = val[6:]
            return self.binaryVal(int(binLen))

        return dict.__getitem__(self, val)

# base Cursor class. All backend drivers are expected to provide this
# interface
class BaseCursor:
    binaryClass = BaseBinary
    def __init__(self, dbh=None):
        self.dbh = dbh
        self._cursor = self._getCursor()

    # map some attributes back to self._cursor
    def __getattr__(self, name):
        if name in  set(["description", "lastrowid"]):
            return getattr(self._cursor, name)
        raise AttributeError("'%s' attribute is invalid" % (name,))

    def lastid(self):
        # wrapper for the lastrowid attribute.
        if hasattr(self._cursor, "lastrowid"):
            return self._cursor.lastrowid
        raise AttributeError("This driver does not know about `lastrowid`")

    # this will need to be provided by each separate driver
    def _getCursor(self):
        assert(self.dbh)
        return self.dbh.cursor()

    # these should be obsoleted soon...
    def binary(self, s):
        if s is None:
            return None
        return self.binaryClass(s)
    def frombinary(self, s):
        return s

    # this needs to be provided by the specific drivers
    def _tryExecute(self, *args, **kw):
        raise NotImplementedError("This function should be provided by the SQL drivers")

    # normalize the execute args and kwargs for passing into the driver
    # on return is a tuple that contains all the positional parameters
    # and kwargs is a hash of all the named arguments passed in
    def _executeArgs(self, args, kw):
        assert(isinstance(args, tuple))
        assert(isinstance(kw, dict))
        if len(args) == 0:
            return (), kw
        # unwrap unwanted encapsulation
        if len(args) == 1:
            if isinstance(args[0], dict):
                kw.update(args[0])
                return (), kw
            if isinstance(args[0], tuple):
                args = args[0]
            elif isinstance(args[0], list):
                args = tuple(args[0])
        return args, kw

    # basic sanity checks for executes
    def _executeCheck(self, sql):
        assert(len(sql) > 0)
        assert(self.dbh and self._cursor)
        return 1

    # basic execute functionality. Usually redefined by the drivers
    def execute(self, sql, *args, **kw):
        self._executeCheck(sql)
        # process the query args
        args, kw = self._executeArgs(args, kw)
        # force dbi compliance here. we prefer args over the kw
        if len(args) == 0:
            return self._tryExecute(self._cursor.execute, sql, **kw)
        if len(kw):
            raise sqlerrors.CursorError(
                "Do not pass both positional and named bind arguments",
                *args, **kw)
        return self._tryExecute(self._cursor.execute, sql, *args)

    # passthrough for the driver's optimized executemany()
    def executemany(self, sql, argList):
        self._executeCheck(sql)
        return self._cursor.executemany(sql.strip(), argList)

    def compile(self, sql):
        return sql

    def execstmt(self, sql, *args):
        return self.execute(sql, *args)

    # return a list of the field names for the last select (if any)
    def fields(self):
        if not self._cursor.description:
            return None
        return [ x[0] for x in self._cursor.description ]

    # return the column names of the current select
    def __rowDict(self, row):
        assert(self._cursor)
        if row is None:
            return None
        if len(row) != len(self._cursor.description):
            raise sqlerrors.CursorError("Cursor description doew not match row data",
                                     row = row, desc = self._cursor.description)
        return dict(zip(self.fields(), row))

    # (a,b)
    def fetchone(self):
        return self._cursor.fetchone()
    # [(a1,b1),(a2, b2)]
    def fetchall(self):
        return list(self._cursor.fetchall())
    def fetchmany(self, count=1):
        return list(self._cursor.fetchmany(count))

    # { name_a : a, name_b : b }
    def fetchone_dict(self):
        return self.__rowDict(self.fetchone())
    # [ {name_a:a1, name_b:b1}, {name_a:a2, name_b:b2} ]
    def fetchall_dict(self):
        return [ self.__rowDict(row) for row in self.fetchall() ]
    def fetchmany_dict(self, count=1):
        return [ self.__rowDict(row) for row in self.fetchmany(count) ]

    def __iter__(self):
        return self

    def next(self):
        item = self.fetchone()
        if item is None:
            raise StopIteration
        else:
            return item

# A class for working with sequences
class BaseSequence:
    def __init__(self, db, name):
        assert(name)
        self.db = db
        self.name = name
        self.seqName = "%s_sequence" % (name,)
        self.__currval = None

    # if we have not called nextval() yet, then currval should be
    # undefined. To easily catch places where we might be doing that,
    # we raise an exception
    def currval(self):
        if self.__currval is None:
            raise sqlerrors.CursorError(
                "Sequence has currval undefined until nextval() is called",
                self.name)
        return self.__currval
    # this is meant to be provided by the drivers
    def nextval(self):
        pass
    # Enforce garbage collection to avoid circular deps
    def __del__(self):
        self.db = self.cu = None

# A class to handle database operations
class BaseDatabase:
    # need to figure out a statement generic enough for all kinds of backends
    alive_check = "select 1 where 1 = 1"
    basic_transaction = "begin transaction"
    cursorClass = BaseCursor
    sequenceClass = BaseSequence
    driver = "base"
    keywords = BaseKeywordDict()
    poolmode = False    # indicates if connections are pooled and can be open/closed cheaply
    
    # schema caching
    tables = None
    views = None
    tempTables = None
    functions = None
    sequences = None
    triggers = None
    version = 0

    def __init__(self, db):
        assert(db)
        self.database = db
        self.dbh = None
        # stderr needs to be around to print errors. hold a reference
        self.stderr = sys.stderr
        self.closed = True
        self.tempTables = sqllib.CaselessDict()
        self.dbName = None

    # close the connection when going out of scope
    def __del__(self):
        self.stderr = self.tempTables = None
        try:
            self.dbh.close()
        except:
            pass
        self.dbh = self.database = None
        self.closed = True

    # the string syntax for database connection is [[user[:password]@]host[:port]/]database
    def _connectData(self, names = ["user", "password", "host", "port", "database"]):
        assert(self.database)
        assert(len(tuple(names)) == 5)
        # regexes are k001 and I am 1337 h@x0r
        regex = re.compile(
            "^(((?P<%s>[^:]+)(:(?P<%s>[^@]+)?)?@)?(?P<%s>[^/:]+)(:(?P<%s>[^/]+))?/)?(?P<%s>.+)$" % tuple(names)
            )
        m = regex.match(self.database.strip())
        assert(m)
        ret = m.groupdict()
        # names[3] == "port" specification
        if ret[names[3]] is not None:
            ret[names[3]] = int(ret[names[3]])
        # names[4] == "dbName"
        self.dbName = ret[names[4]]
        return ret

    def connect(self, **kwargs):
        assert(self.database)
        raise RuntimeError("This connect function has to be provided by the database driver")

    # reopens the database backend, if required.
    # makes most sense for sqlite-type backends; for networked backends it pings/reconnects
    def reopen(self):
        """Returns True if the database backend was reopened or a reconnection
        was required"""
        if self.dbh and self.alive():
            return False
        return self.connect()

    def close(self):
        # clean up schema structures
        self.tables = self.views = self.tempTables = None
        self.functions = self.sequences = self.triggers = None
        self.version = 0
        if self.dbh:
            self.dbh.close()
        self.dbh = None
        self.closed = True

    def alive(self):
        if not self.dbh:
            return False
        try:
            c = self.cursor()
            c.execute(self.alive_check)
        except:
            # database connection lost
            return False
        else:
            del c
        return True

    # creating cursors
    def cursor(self):
        assert (self.dbh)
        return self.cursorClass(self.dbh)
    itercursor = cursor

    def sequence(self, name):
        assert(self.dbh)
        return self.sequenceClass(self, name)

    # perform the equivalent of a analyze on $self
    def analyze(self, table=""):
        assert(self.database)
        pass

    # transaction support
    def _logTransaction(self, command):
        """
        Check for txn sanity, when configured to do so.
        """
        # pylint: disable-msg=W0212
        #  * _getframe needed to make a nicer stack dump.
        assert command in ('BEGIN', 'ROLLBACK', 'COMMIT')
        if DEBUG_TRANSACTIONS == DEBUG_OFF:
            return
        shouldBeInTrans = (command != 'BEGIN')
        inTrans = self.inTransaction(default=shouldBeInTrans)
        if inTrans == shouldBeInTrans:
            if DEBUG_TRANSACTIONS == DEBUG_WARN_ALL:
                print >> sys.stderr, 'Transaction: %s at' % (command,)
                traceback.print_stack(sys._getframe(2))
            return

        where = (inTrans and 'inside' or 'outside')
        if DEBUG_TRANSACTIONS == DEBUG_ERROR:
            print >> sys.stderr, 'Transaction bug: %s %s of transaction' % (command, where)
            from conary.lib import debugger
            debugger.st()
        else:
            print >> sys.stderr, 'Transaction bug: %s %s of transaction at:' % (command, where)
            traceback.print_stack(sys._getframe(2))

    def commit(self):
        assert(self.dbh)
        self._logTransaction('COMMIT')
        return self.dbh.commit()

    def transaction(self, name = None):
        "start transaction [ named point ]"
        # basic class does not support savepoints
        assert(not name)
        assert(self.dbh)
        self._logTransaction('BEGIN')
        c = self.cursor()
        c.execute(self.basic_transaction)
        return c

    def rollback(self, name=None):
        "rollback [ to transaction point ]"
        # basic class does not support savepoints
        assert(not name)
        assert(self.dbh)
        self._logTransaction('ROLLBACK')
        return self.dbh.rollback()

    @staticmethod
    def inTransaction(default=None):
        """
        Return C{True} if the connection currently has an active
        transaction.

        If C{default} is not C{None}, return C{default} if the database
        engine does not have a working implementation of this method.
        Otherwise, raises C{NotImplementedError}.
        """
        if default is not None:
            return default
        raise NotImplementedError("This function should be provided by the SQL drivers")

    # trigger schema handling
    def createTrigger(self, table, when, onAction, sql):
        assert(table in self.tables)
        name = "%s_%s" % (table, onAction)
        if name in self.triggers:
            return False
        sql = """
        CREATE TRIGGER %s %s %s ON %s
        FOR EACH ROW BEGIN
        %s
        END
        """ % (name, when.upper(), onAction.upper(), table, sql)
        cu = self.dbh.cursor()
        cu.execute(sql)
        self.triggers[name] = table
        return True
    def dropTrigger(self, table, onAction):
        onAction = onAction.lower()
        name = "%s_%s" % (table, onAction)
        if name not in self.triggers:
            return False
        cu = self.dbh.cursor()
        cu.execute("DROP TRIGGER %s" % name)
        del self.triggers[name]
        return True

    # index schema handling
    def createIndex(self, table, name, columns, unique = False,
                    check = True):
        if unique:
            unique = "UNIQUE"
        else:
            unique = ""
        if check:
            assert(table in self.tables)
            if name in self.tables[table]:
                return False
        sql = "CREATE %s INDEX %s on %s (%s)" % (
            unique, name, table, columns)
        cu = self.dbh.cursor()
        cu.execute(sql)
        return True
    def _dropIndexSql(self, table, name):
        sql = "DROP INDEX %s" % (name,)
        cu = self.dbh.cursor()
        cu.execute(sql)
    def dropIndex(self, table, name, check = True):
        if check:
            assert(table in self.tables)
            if name not in self.tables[table]:
                return False
        self._dropIndexSql(table, name)
        try:
            self.tables[table].remove(name)
        except ValueError, e:
            pass
        return True

    # since not all databases handle renaming and dropping columns the
    # same way, we provide a more generic interface in here
    def dropColumn(self, table, name):
        assert(self.dbh)
        sql = "ALTER TABLE %s DROP COLUMN %s" % (table, name)
        cu = self.dbh.cursor()
        cu.execute(sql)
        return True
    def renameColumn(self, table, oldName, newName):
        # avoid busywork
        if oldName.lower() == newName.lower():
            return True
        assert(self.dbh)
        sql = "ALTER TABLE %s RENAME COLUMN %s TO %s" % (table, oldName, newName)
        cu = self.dbh.cursor()
        cu.execute(sql)
        return True

    # easy access to the schema state
    def loadSchema(self):
        assert(self.dbh)
        # keyed by table, values are indexes on the table
        self.tables = sqllib.CaselessDict()
        self.views = sqllib.CaselessDict()
        self.functions = sqllib.CaselessDict()
        self.sequences = sqllib.CaselessDict()
        self.triggers = sqllib.CaselessDict()
        self.version = 0

    def getVersion(self, raiseOnError=False):
        """
        Get the current schema version. If the version table is not
        present, return a zero version.

        @param raiseOnError: If set, raise instead of returning zero if 
                the table is missing.
        @type  raiseOnError: C{bool}
        @rtype L{DBversion<conary.dbstore.sqllib.DBversion>}
        """

        assert(self.dbh)
        c = self.cursor()

        # If self.tables is non-empty, loadSchema() has probably been
        # called, so we can do a fast (and non-intrusive) check for
        # our table.
        if self.tables and 'DatabaseVersion' not in self.tables:
            self.version = sqllib.DBversion(0, 0)
            return self.version

        # Otherwise, the schema might not be loaded so use a try/except
        # pattern.

        # DatabaseVersion canbe an old style table that has only a version column
        # or it could be a new style version that has (version, minor) columns
        # or it can be a mint table that has (version, timestamps) columns
        try:
            c.execute("select * from DatabaseVersion limit 1")
        except sqlerrors.InvalidTable:
            if raiseOnError:
                raise
            self.version = sqllib.DBversion(0,0)
            return self.version
        # keep compatibility with old style table versioning
        ret = c.fetchone_dict()
        if ret is None: # no version record found...
            self.version = sqllib.DBversion(0,0)
        elif ret.has_key("minor"): # assume new style
            self.version = sqllib.DBversion(ret["version"], ret["minor"])
        else: # assume mint/old style
            c.execute("select max(version) from DatabaseVersion")
            self.version = sqllib.DBversion(c.fetchone()[0])
        return self.version

    def setVersion(self, version, skipCommit=False):
        assert(self.dbh)
        if isinstance(version, int):
            version = sqllib.DBversion(version)
        elif isinstance(version, tuple):
            version = sqllib.DBversion(*version)
        assert (isinstance(version, sqllib.DBversion))
        c = self.cursor()
        crtVersion = self.getVersion()
        # test if we have the old style database version and update
        if crtVersion > 0 and crtVersion.minor == 0:
            c.execute("select * from DatabaseVersion")
            ret = c.fetchone()
            if len(ret) == 1: # old style, one number
                c.execute("drop table DatabaseVersion")
                crtVersion = 0 # mark for re-creation
        # do not allow "going back"
        assert (version >= crtVersion)
        if crtVersion == 0: # indicates table is not there
            c.execute("CREATE TABLE DatabaseVersion (version INTEGER, minor INTEGER)")
            c.execute("INSERT INTO DatabaseVersion (version, minor) VALUES (?,?)",
                      (version.major, version.minor))
            if not skipCommit:
                self.commit()
            self.tables['DatabaseVersion'] = []
            return version
        c.execute("UPDATE DatabaseVersion SET version = ?, minor = ?",
                  (version.major, version.minor))
        if not skipCommit:
            self.commit()
        return version

    def shell(self):
        import shell
        shell.shell(self)

    def use(self, dbName, **kwargs):
        """ Connects to a new database using the same login credentials and database host.
        On sqlite, this emulates a straight new connect() """
        raise RuntimeError("This function has to be provided by the database driver")

    # faster data load for large tables. by default we redirect to executemany()
    def bulkload(self, tableName, rows, columnNames, start_transaction = True):
        cu = self.cursor()
        cols = ",".join(columnNames)
        values = ",".join("?" for x in range(len(columnNames)))
        return cu.executemany("insert into %s (%s) values (%s)" % (
            tableName, cols, values), rows,
                              start_transaction = start_transaction)
        
    # foreign key constraint management
    def addForeignKey(self, table, column, refTable, refColumn,
                      cascade = False, name = None):
        onDelete = "RESTRICT"
        if cascade:
            onDelete = "CASCADE"
        # we always cascade on updates...
        onUpdate = "CASCADE"
        if name is None:
            # by convention, foreign keys are named <table>_<column>_fk
            name = "%s_%s_fk" % (table, column)
        assert (table in self.tables)
        assert (refTable in self.tables)
        cu = self.cursor()
        cu.execute("""
        ALTER TABLE %s ADD CONSTRAINT %s
            FOREIGN KEY (%s) REFERENCES %s(%s)
            ON UPDATE %s ON DELETE %s """ %(
            table, name, column, refTable, refColumn,
            onUpdate, onDelete))
        return True
    def dropForeignKey(self, table, column = None, name = None):
        assert (table in self.tables)
        if name is None:
            assert (column is not None), "column name required to build FK name"
            # by convention, foreign keys are named <table>_<column>_fk
            name = "%s_%s_fk" % (table, column)
        cu = self.cursor()
        cu.execute("ALTER TABLE %s DROP CONSTRAINT %s" % (table, name))
        return True

    # resetting the auto increment values of primary keys
    def setAutoIncrement(self, table, column, value):
        raise NotImplementedError("This function should be provided by the SQL drivers")
    
