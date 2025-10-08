# Test EXPLAIN ANALYZE with invisible rows from concurrent transactions

setup
{
    CREATE TABLE test_invisible_table_seq_scan (id numeric, data text);
    INSERT INTO test_invisible_table_seq_scan VALUES (1, 'initial1'), (2, 'initial2');

    CREATE TABLE test_invisible_rows_bitmap_heap_and_index_scan (
        id numeric,
        data TEXT
    );
    CREATE INDEX idx_test_invisible_rows_id ON test_invisible_rows_bitmap_heap_and_index_scan(id);

    CREATE INDEX idx_test_invisible_rows_covering ON test_invisible_rows_bitmap_heap_and_index_scan(id) INCLUDE (data);

    INSERT INTO test_invisible_rows_bitmap_heap_and_index_scan VALUES (1, 'initial1'), (2, 'initial2');

    CREATE TABLE p1 (c1 numeric);
    INSERT INTO p1 SELECT 123 FROM generate_series(1,1000);
    
    CREATE TABLE p2 (c1 numeric);
    INSERT INTO p2 SELECT 123 FROM generate_series(1,1000);
}

teardown
{
    DROP TABLE test_invisible_table_seq_scan;
    DROP TABLE test_invisible_rows_bitmap_heap_and_index_scan;
    DROP TABLE p1;
    DROP TABLE p2;
}

session "updater"
step "s1_begin" { BEGIN; }
step "s1_update_row1" { UPDATE test_invisible_table_seq_scan SET data = 'updated1' WHERE id = 1; }
step "s1_delete_row1" { DELETE FROM test_invisible_table_seq_scan WHERE id = 1; }
step "s1_insert_row_index" { INSERT INTO test_invisible_rows_bitmap_heap_and_index_scan VALUES (3, 'initial3'), (4, 'initial4'), (5, 'initial5'); }
step "s1_insert_many_row_index" { INSERT INTO test_invisible_rows_bitmap_heap_and_index_scan (id, data) SELECT i, 'initial' || i FROM generate_series(6, 10005) AS i; }
step "s1_insert_many_rows_p1" { INSERT INTO p1 SELECT 123 FROM generate_series(1, 1000000); }
step "s1_commit" { COMMIT; }

session "explainer"  
step "s2_begin" { BEGIN; }
step "s2_explain" { EXPLAIN (ANALYZE, INV_ROWS, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT * FROM test_invisible_table_seq_scan; }
step "s2_set_seqscan_and_bitmap_scan_off" { SET enable_seqscan = off; SET enable_bitmapscan = off; }
step "s2_set_seqscan_and_bitmap_scan_on" { SET enable_seqscan = on; SET enable_bitmapscan = on; }
step "s2_set_indexonly_scan_off" { SET enable_indexonlyscan = off; }
step "s2_set_indexonly_scan_on" { SET enable_indexonlyscan = on; }
step "s2_explain_bitmap_and_index" { EXPLAIN (ANALYZE, INV_ROWS, COSTS OFF, TIMING OFF, SUMMARY OFF) 
                                     SELECT * FROM test_invisible_rows_bitmap_heap_and_index_scan 
                                     WHERE id >= 1 AND id <= 6000; }
step "s2_explain_index_only_covering" { EXPLAIN (ANALYZE, INV_ROWS, COSTS OFF, TIMING OFF, SUMMARY OFF)
                                        SELECT id, data FROM test_invisible_rows_bitmap_heap_and_index_scan 
                                        WHERE id >= 1 AND id <= 6000; }
step "s2_explain_parallel_scan" { 
    SET max_parallel_workers_per_gather = 4;
    EXPLAIN (ANALYZE, INV_ROWS, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT COUNT(*) FROM p1 join p2 on p1.c1 = p2.c1; 
    }
step "s2_set_read_committed" { SET TRANSACTION ISOLATION LEVEL READ COMMITTED; }
step "s2_commit" { COMMIT; }

# Test Case 1: Explain sees updated row as invisible
permutation "s2_begin" "s1_begin" "s1_update_row1" "s2_explain" "s2_commit" "s1_commit"

# Test Case 2: Explain sees deleted row as visible
permutation "s2_begin" "s1_begin" "s1_delete_row1" "s2_explain" "s2_commit" "s1_commit"

# Test Case 3: Explain sees inserted rows as invisible in bitmap heap scan
permutation "s2_begin" "s1_begin" "s1_insert_row_index" "s2_explain_bitmap_and_index" "s2_commit" "s1_commit"

# Test Case 4: Explain sees inserted rows as invisible in index scan
permutation "s2_begin" "s1_begin" "s1_insert_many_row_index" "s2_set_seqscan_and_bitmap_scan_off" "s2_set_indexonly_scan_off" "s2_explain_bitmap_and_index" "s2_set_seqscan_and_bitmap_scan_on" "s2_set_indexonly_scan_on" "s2_commit" "s1_commit"

# Test Case 7: Explain sees inserted rows as invisible in index only scan
permutation "s2_begin" "s1_begin" "s1_insert_many_row_index" "s2_set_seqscan_and_bitmap_scan_off" "s2_explain_index_only_covering" "s2_set_seqscan_and_bitmap_scan_on" "s2_commit" "s1_commit"

# Test Case 8: Explain sees inserted rows as invisible in parallel seq scan
permutation "s2_begin" "s1_begin" "s1_insert_many_rows_p1" "s2_explain_parallel_scan" "s2_commit" "s1_commit"

# Test Case 9: Vacuum removes invisible rows
permutation "s2_begin" "s2_set_read_committed" "s1_begin" "s1_insert_row_index" "s2_explain_bitmap_and_index" "s1_commit" "s2_explain_bitmap_and_index" "s2_commit" "s2_explain_bitmap_and_index"
