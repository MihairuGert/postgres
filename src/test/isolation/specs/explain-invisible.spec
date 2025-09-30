# Test EXPLAIN ANALYZE with invisible rows from concurrent transactions

setup
{
    CREATE TABLE test_invisible (id int PRIMARY KEY, data text);
    INSERT INTO test_invisible VALUES (1, 'initial1'), (2, 'initial2');
}

teardown
{
    DROP TABLE test_invisible;
}

session "updater"
step "s1_begin" { BEGIN; }
step "s1_update_row1" { UPDATE test_invisible SET data = 'updated1' WHERE id = 1; }
step "s1_commit" { COMMIT; }

session "explainer"  
step "s2_begin" { BEGIN; }
step "s2_explain" { EXPLAIN (ANALYZE, INV_ROWS, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT * FROM test_invisible; }
step "s2_commit" { COMMIT; }

# Test Case 1: Explain sees updated row as invisible
permutation "s2_begin" "s1_begin" "s1_update_row1" "s2_explain" "s2_commit" "s1_commit"
