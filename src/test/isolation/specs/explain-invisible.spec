# Test EXPLAIN ANALYZE with invisible rows from concurrent transactions

setup
{
    CREATE TABLE test_invisible_table_seq_scan (id int PRIMARY KEY, data text);
    INSERT INTO test_invisible_table_seq_scan VALUES (1, 'initial1'), (2, 'initial2');

    CREATE TABLE test_invisible_rows_bitmap_heap_and_index_scan (
        id SERIAL PRIMARY KEY,
        data TEXT
    );
    CREATE INDEX idx_test_invisible_rows_id ON test_invisible_rows_bitmap_heap_and_index_scan(id);

    INSERT INTO test_invisible_rows_bitmap_heap_and_index_scan VALUES (1, 'initial1'), (2, 'initial2');
}

teardown
{
    DROP TABLE test_invisible_table_seq_scan;
    DROP TABLE test_invisible_rows_bitmap_heap_and_index_scan;
}

session "updater"
step "s1_begin" { BEGIN; }
step "s1_update_row1" { UPDATE test_invisible_table_seq_scan SET data = 'updated1' WHERE id = 1; }
step "s1_delete_row1" { DELETE FROM test_invisible_table_seq_scan WHERE id = 1; }
step "s1_insert_row_index" { INSERT INTO test_invisible_rows_bitmap_heap_and_index_scan VALUES (3, 'initial3'), (4, 'initial4'), (5, 'initial5'); }
step "s1_insert_many_row_index" { INSERT INTO test_invisible_rows_bitmap_heap_and_index_scan (id, data) SELECT i, 'initial' || i FROM generate_series(6, 10005) AS i; }
step "s1_commit" { COMMIT; }

session "explainer"  
step "s2_begin" { BEGIN; }
step "s2_explain" { EXPLAIN (ANALYZE, INV_ROWS, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT * FROM test_invisible_table_seq_scan; }
step "s2_set_seqscan_and_bitmap_scan_off" { SET enable_seqscan = off; SET enable_bitmapscan = off; }
step "s2_set_seqscan_and_bitmap_scan_on" { SET enable_seqscan = on; SET enable_bitmapscan = on; }
step "s2_explain_bitmap_and_index" { EXPLAIN (ANALYZE, INV_ROWS, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT * FROM test_invisible_rows_bitmap_heap_and_index_scan WHERE id >= 6 AND id <= 6000 ORDER BY id; }
step "s2_commit" { COMMIT; }

# Test Case 1: Explain sees updated row as invisible
permutation "s2_begin" "s1_begin" "s1_update_row1" "s2_explain" "s2_commit" "s1_commit"

# Test Case 2: Explain sees deleted row as visible
permutation "s2_begin" "s1_begin" "s1_delete_row1" "s2_explain" "s2_commit" "s1_commit"

# Test Case 3: Explain sees inserted rows as invisible in bitmap heap scan
permutation "s2_begin" "s1_begin" "s1_insert_row_index" "s2_explain_bitmap_and_index" "s2_commit" "s1_commit"

# Test Case 4: Explain sees inserted rows as invisible in index scan
permutation "s2_begin" "s1_begin" "s1_insert_many_row_index" "s2_set_seqscan_and_bitmap_scan_off" "s2_explain_bitmap_and_index" "s2_set_seqscan_and_bitmap_scan_on" "s2_commit" "s1_commit"
