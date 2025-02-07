.. _ref_eql_ddl_object_types:

============
Object Types
============

This section describes the DDL commands pertaining to
:ref:`object types <ref_datamodel_object_types>`.


CREATE TYPE
===========

:eql-statement:
:eql-haswith:


:ref:`Define <ref_eql_sdl_object_types>` a new object type.

.. eql:synopsis::

    [ WITH <with-item> [, ...] ]
    CREATE [ABSTRACT] TYPE <name> [ EXTENDING <supertype> [, ...] ]
    [ "{" <subcommand>; [...] "}" ] ;

    # where <subcommand> is one of

      CREATE ANNOTATION <annotation-name> := <value>
      CREATE LINK <link-name> ...
      CREATE PROPERTY <property-name> ...
      CREATE CONSTRAINT <constraint-name> ...
      CREATE INDEX ON <index-expr>

Description
-----------

``CREATE TYPE`` defines a new object type for use in the current database.

If *name* is qualified with a module name, then the type is created
in that module, otherwise it is created in the current module.
The type name must be distinct from that of any existing schema item
in the module.

Parameters
----------

Most sub-commands and options of this command are identical to the
:ref:`SDL object type declaration <ref_eql_sdl_object_types_syntax>`,
with some additional features listed below:

:eql:synopsis:`WITH <with-item> [, ...]`
    Alias declarations.

    The ``WITH`` clause allows specifying module aliases
    that can be referenced by the command.  See :ref:`ref_eql_statements_with`
    for more information.

The following subcommands are allowed in the ``CREATE TYPE`` block:

:eql:synopsis:`CREATE ANNOTATION <annotation-name> := <value>`
    Set object type :eql:synopsis:`<annotation-name>` to
    :eql:synopsis:`<value>`.

    See :eql:stmt:`CREATE ANNOTATION` for details.

:eql:synopsis:`CREATE LINK <link-name> ...`
    Define a new link for this object type.  See
    :eql:stmt:`CREATE LINK` for details.

:eql:synopsis:`CREATE PROPERTY <property-name> ...`
    Define a new property for this object type.  See
    :eql:stmt:`CREATE PROPERTY` for details.

:eql:synopsis:`CREATE CONSTRAINT <constraint-name> ...`
    Define a concrete constraint for this object type.  See
    :eql:stmt:`CREATE CONSTRAINT` for details.

:eql:synopsis:`CREATE INDEX ON <index-expr>`
    Define a new :ref:`index <ref_datamodel_indexes>`
    using *index-expr* for this object type.  See
    :eql:stmt:`CREATE INDEX` for details.

Examples
--------

Create an object type ``User``:

.. code-block:: edgeql

    CREATE TYPE User {
        CREATE PROPERTY name -> str;
    };


.. _ref_eql_ddl_object_types_alter:

ALTER TYPE
==========

:eql-statement:
:eql-haswith:


Change the definition of an
:ref:`object type <ref_datamodel_object_types>`.

.. eql:synopsis::

    [ WITH <with-item> [, ...] ]
    ALTER TYPE <name>
    [ "{" <subcommand>; [...] "}" ] ;

    [ WITH <with-item> [, ...] ]
    ALTER TYPE <name> <subcommand> ;

    # where <subcommand> is one of

      RENAME TO <newname>
      EXTENDING <parent> [, ...]
      CREATE ANNOTATION <annotation-name> := <value>
      ALTER ANNOTATION <annotation-name> := <value>
      DROP ANNOTATION <annotation-name>
      CREATE LINK <link-name> ...
      ALTER LINK <link-name> ...
      DROP LINK <link-name> ...
      CREATE PROPERTY <property-name> ...
      ALTER PROPERTY <property-name> ...
      DROP PROPERTY <property-name> ...
      CREATE CONSTRAINT <constraint-name> ...
      ALTER CONSTRAINT <constraint-name> ...
      DROP CONSTRAINT <constraint-name> ...
      CREATE INDEX ON <index-expr>
      DROP INDEX ON <index-expr>


Description
-----------

``ALTER TYPE`` changes the definition of an object type.
*name* must be a name of an existing object type, optionally qualified
with a module name.

Parameters
----------

The following subcommands are allowed in the ``ALTER TYPE`` block:

:eql:synopsis:`WITH <with-item> [, ...]`
    Alias declarations.

    The ``WITH`` clause allows specifying module aliases
    that can be referenced by the command.  See :ref:`ref_eql_statements_with`
    for more information.

:eql:synopsis:`<name>`
    The name (optionally module-qualified) of the type being altered.

:eql:synopsis:`EXTENDING <parent> [, ...]`
    Alter the supertype list.  The full syntax of this subcommand is:

    .. eql:synopsis::

         EXTENDING <parent> [, ...]
            [ FIRST | LAST | BEFORE <exparent> | AFTER <exparent> ]

    This subcommand makes the type a subtype of the specified list
    of supertypes.  The requirements for the parent-child relationship
    are the same as when creating an object type.

    It is possible to specify the position in the parent list
    using the following optional keywords:

    * ``FIRST`` -- insert parent(s) at the beginning of the
      parent list,
    * ``LAST`` -- insert parent(s) at the end of the parent list,
    * ``BEFORE <parent>`` -- insert parent(s) before an
      existing *parent*,
    * ``AFTER <parent>`` -- insert parent(s) after an existing
      *parent*.

:eql:synopsis:`ALTER ANNOTATION <annotation-name>;`
    Alter object type annotation :eql:synopsis:`<annotation-name>`.
    See :eql:stmt:`ALTER ANNOTATION <ALTER ANNOTATION>` for details.

:eql:synopsis:`DROP ANNOTATION <annotation-name>`
    Remove object type :eql:synopsis:`<annotation-name>`.
    See :eql:stmt:`DROP ANNOTATION <DROP ANNOTATION>` for details.

:eql:synopsis:`ALTER LINK <link-name> ...`
    Alter the definition of a link for this object type.  See
    :eql:stmt:`ALTER LINK` for details.

:eql:synopsis:`DROP LINK <link-name>`
    Remove a link item from this object type.  See
    :eql:stmt:`DROP LINK` for details.

:eql:synopsis:`ALTER PROPERTY <property-name> ...`
    Alter the definition of a property item for this object type.
    See :eql:stmt:`ALTER PROPERTY` for details.

:eql:synopsis:`DROP PROPERTY <property-name>`
    Remove a property item from this object type.  See
    :eql:stmt:`DROP PROPERTY` for details.

:eql:synopsis:`ALTER CONSTRAINT <constraint-name> ...`
    Alter the definition of a constraint for this object type.  See
    :eql:stmt:`ALTER CONSTRAINT` for details.

:eql:synopsis:`DROP CONSTRAINT <constraint-name>;`
    Remove a constraint from this object type.  See
    :eql:stmt:`DROP CONSTRAINT` for details.

:eql:synopsis:`DROP INDEX ON <index-expr>`
    Remove an :ref:`index <ref_datamodel_indexes>` defined as *index-expr*
    from this object type.  See :eql:stmt:`DROP INDEX` for details.

All the subcommands allowed in the ``CREATE TYPE`` block are also
valid subcommands for ``ALTER TYPE`` block.

Examples
--------

Alter the ``User`` object type to make ``name`` required:

.. code-block:: edgeql

    ALTER TYPE User {
        ALTER PROPERTY name {
            SET REQUIRED;
        }
    };


DROP TYPE
=========

:eql-statement:
:eql-haswith:


Remove the specified object type from the schema.

.. eql:synopsis::

    DROP TYPE <name> ;

Description
-----------

``DROP TYPE`` removes the specified object type from the schema.
schema.  All subordinate schema items defined on this type, such
as links and indexes, are removed as well.

Examples
--------

Remove the ``User`` object type:

.. code-block:: edgeql

    DROP TYPE User;

.. list-table::
  :class: seealso

  * - **See also**
  * - :ref:`Schema > Object types <ref_datamodel_object_types>`
  * - :ref:`SDL > Object types <ref_eql_sdl_object_types>`
  * - :ref:`Introspection > Object types <ref_eql_introspection_object_types>`
  * - :ref:`Cheatsheets > Object types <ref_cheatsheet_object_types>`
