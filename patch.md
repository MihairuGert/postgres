# Patch for PostgreSQL 18: Invisible Rows option in EXPLAIN ANALYZE

## Overview

This patch introduces a new feature for the **EXPLAIN** command. The main goal is to allow users to count the number of accesses to rows that are hidden in the current Multi-Version Concurrency Control (MVCC) snapshot (also known as "invisible"). This new addition provides a new system metric that can be helpful for PostgreSQL administrators and developers.

**Primary Author:** Pyatanov M.Y.
**Contributors:** Bondar A.M.
**Related GitHub:** `https://github.com/MihairuGert/postgres/tree/invisible_rows`
**Target PostgreSQL Version:** 18

---

## Table of Contents

1.  [Functional Description](#functional-description)
2.  [Technical Implementation](#technical-implementation)
3.  [Usage and Examples](#usage-and-examples)
4.  [Backward Compatibility](#backward-compatibility)
5.  [Performance Impact](#performance-impact)
6.  [Testing](#testing)

---

## Functional Description

*   **Problem Statement:** During the process of query execution, invisible rows are inevitably read and verificated for visibility, resulting in a performance degradation. At present, there exists no precise method in PostgreSQL to accurately estimate the number of accesses made to these rows during the execution of a single query.
*   **Solution Summary:** In order to address this issue, it is suggested to implement a counter that tracks the number of accesses to invisible rows. This counter can be activated by the `INV_ROWS` option in `EXPLAIN ANALYZE` command.
*   **Key Benefits:**
    *   Allows to track long transactions and MVCC overhead incurred by the query.
    *   Allows to detect a large work flow with tables.
    *   Allows to discover an increased table bloat.

## Technical Implementation

*   **Architectural Changes:**
    *   New structure `InvRowsUsage` was added to `Instrumentation` struct fields. It contains `inv_rows` field incremented in function `HeapTupleSatisfiesVisibility` when `HeapTupleSatisfiesMVCC` returns false.
    *   New arguments were added to `InstrEndParallelQuery` and `InstrAccumParallelQuery` which help to accumulate invisible rows statistics in parallel queries.
    *   The signature change of `InstrEndParallelQuery` and `InstrAccumParallelQuery` led to addition of new field to `BrinLeader`, `GinLeader`, `BTLeader`, `ParallelVacuumState`, `ParallelExecutorInfo` containing a pointer to `InvRowsUsage` struct.
    *   New option `INV_ROWS` was added to `EXPLAIN` command (can only be used with `ANALYZE` option). It adds the information about invisible rows usage to `ExplainNode` output. 
*   **Modified Files:**
    *   `src/include/executor/instrument.h` - new structure `InvRowsUsage`, new fields `invrowsusage_start`, `invrowsusage`, `need_invrowsusage` in `Instrumentation` were added.
    *   `src/backend/executor/instrument.c` - invisible rows aggregation based on WAL and Buffer usage aggregation principles was implemented.
    *   `src/backend/commands/explain.c` - invisible rows usage information to the `EXPLAIN` output was added.
    *   `src/backend/commands/explain_state.c` - `ParseExplainOptionList` was changed to handle `INV_ROWS` option. 
    *   `src/include/commands/explain_state.h` - new option `inv_rows` in ExplainState struct. 
    *   `src/backend/access/heap/heapam_visibility.c` - catching `HeapTupleSatisfiesMVCC` return value in order to increment `InvRowsUsage` counter.
    *   `src/backend/access/brin/brin.c`, `src/backend/access/gin/gininsert.c`, `src/backend/access/nbtree/nbtsort.c`, `src/backend/commands/vacuumparallel.c`, `src/include/executor/execParallel.h` - A new region in shared memory to store `InvRowsUsage` was added as well as new fields in structs mentioned above.  
    *   `doc/src/sgml/ref/explain.sgml` - Documentation updates.
    *   `src/test/isolation/isolation_schedule` - added new isolation test `explain-invisible`. 
*   **New Files:**
    * `src/test/isolation/specs/explain-invisible.spec` - new isolation test.
## Usage and Examples

**Basic Syntax**
```sql
EXPLAIN (ANALYZE, INV_ROWS) SELECT * FROM TABLE_NAME;
```

**Example 1**
```sql
-- SESSION 1
CREATE TABLE FOO (C1 NUMERIC);

INSERT INTO FOO SELECT 123 FROM GENERATE_SERIES(1,100);
EXPLAIN (ANALYZE, INV_ROWS, BUFFERS OFF) SELECT * FROM FOO;

-- SESSION 2
BEGIN;
INSERT INTO FOO SELECT 123 FROM GENERATE_SERIES(1,100);

-- SESSION 1
EXPLAIN (ANALYZE, INV_ROWS, BUFFERS OFF) SELECT * FROM FOO;
```

**Sample Output 1**
```text
                                                       QUERY PLAN                                                       
------------------------------------------------------------------------------------------------------------------------
 Seq Scan on foo  (cost=0.00..23.60 rows=1360 width=32) (actual time=0.020..0.029 invisible rows=0 rows=100.00 loops=1)
 Planning Time: 0.051 ms
 Execution Time: 0.041 ms
(3 rows)

                                                      QUERY PLAN                                                       
-----------------------------------------------------------------------------------------------------------------------
 Seq Scan on foo  (cost=0.00..2.00 rows=100 width=5) (actual time=0.048..0.074 invisible rows=100 rows=100.00 loops=1)
 Planning Time: 0.068 ms
 Execution Time: 0.109 ms
(3 rows)
```

**Example 2**
```sql
-- SESSION 1
CREATE TABLE FOO (C1 NUMERIC);
CREATE TABLE BAR (C1 NUMERIC);

INSERT INTO FOO SELECT 123 FROM GENERATE_SERIES(1,100);
INSERT INTO BAR SELECT 123 FROM GENERATE_SERIES(1,1000);

-- SESSION 2
BEGIN;
INSERT INTO FOO SELECT 123 FROM GENERATE_SERIES(1,100);

-- SESSION 1
EXPLAIN (ANALYZE, INV_ROWS, BUFFERS OFF) SELECT * FROM FOO JOIN BAR ON FOO.C1 = BAR.C1;
```

**Sample Output 2**
```text
                                                              QUERY PLAN                                                              
--------------------------------------------------------------------------------------------------------------------------------------
 Merge Join  (cost=188.77..334.29 rows=9248 width=64) (actual time=0.846..44.146 invisible rows=100 rows=100000.00 loops=1)
   Merge Cond: (foo.c1 = bar.c1)
   ->  Sort  (cost=94.38..97.78 rows=1360 width=32) (actual time=0.152..0.159 invisible rows=100 rows=100.00 loops=1)
         Sort Key: foo.c1
         Sort Method: quicksort  Memory: 25kB
         ->  Seq Scan on foo  (cost=0.00..23.60 rows=1360 width=32) (actual time=0.026..0.036 invisible rows=100 rows=100.00 loops=1)
   ->  Sort  (cost=94.38..97.78 rows=1360 width=32) (actual time=0.686..6.362 invisible rows=0 rows=99901.00 loops=1)
         Sort Key: bar.c1
         Sort Method: quicksort  Memory: 25kB
         ->  Seq Scan on bar  (cost=0.00..23.60 rows=1360 width=32) (actual time=0.033..0.242 invisible rows=0 rows=1000.00 loops=1)
 Planning Time: 2.978 ms
 Execution Time: 47.288 ms
(12 rows)
```

## Backward Compatibility

*   **SQL Interface:** New option `INV_ROWS` for `EXPLAIN ANALYZE` was added.
*   **Upgrade/Migration Impact:** Is it safe for the upgrade.

## Performance Impact

*   **Benchmarks:** The measurements were carried out as follows: 
* The timing and summary options are turned off on purpose so that they do not affect the measurement results.
* After initialization, a script was run on the test base that creates invisible rows due to an open transaction in which several insert and update operations were performed.
* The load was applied from 10, 20, 30, 40 and 50 clients in both scenarios. The duration of each test is 60 seconds. 6 runs were performed for each test variant to average the result.

    The measurement results with the option turned on and off are almost identical, which means that it can be concluded that the new option does not introduce significant overhead costs into the system.

## Testing
*   **Isolation Tests:** New test added to the core isolation test suite: `src/test/isolation/specs/explain-invisible.spec`.
*   **Platforms Tested On:** Linux x86_64
