from grantlens_eval.finetune import QUERY_PREFIX, select_pairs

LONG = "word " * 100


def rows():
    return [
        ("1", "Cancer imaging program", LONG), ("2", "Cancer Imaging Program!", LONG),  # same program, written twice
        ("3", "Rural health access grants", LONG), ("4", "Graded evaluation grant", LONG),
        ("5", "Too short abstract", "tiny"), ("6", "Tiny", LONG),
        ("7", "Marine biology research fund", LONG),
    ]


def test_graded_grants_never_enter_training():
    pairs = select_pairs(rows(), exclude={"4"}, n=100)
    assert not any("Graded evaluation grant" in a for a, _ in pairs)


def test_one_pair_per_program_and_junk_is_skipped():
    titles = [a.removeprefix(QUERY_PREFIX).lower().rstrip("!") for a, _ in select_pairs(rows(), exclude=set(), n=100)]
    assert sum("cancer imaging" in t for t in titles) == 1  # the repeated program counts once
    assert not any("too short" in t or t == "tiny" for t in titles)  # short abstracts and titles are dropped


def test_queries_carry_the_retrieval_prefix_documents_do_not_and_the_choice_is_repeatable():
    pairs = select_pairs(rows(), exclude=set(), n=100)
    assert all(a.startswith(QUERY_PREFIX) and not b.startswith(QUERY_PREFIX) for a, b in pairs)
    assert pairs == select_pairs(rows(), exclude=set(), n=100) and len(select_pairs(rows(), exclude=set(), n=2)) == 2
