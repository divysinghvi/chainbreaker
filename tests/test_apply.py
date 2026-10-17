from chainbreaker.demo.apply import edit_lines


def test_edit_only_recorded_lines_and_add_ref_comment():
    text = "a\n      - uses: o/x@v3\n      - uses: o/x@v3\n      - uses: o/y@L1 # v1\n"
    out = edit_lines(text, [2], "o/x@v3", "o/x@" + "a" * 40)
    assert out.splitlines()[1] == "      - uses: o/x@" + "a" * 40 + " # v3"
    assert out.splitlines()[2] == "      - uses: o/x@v3"
    out = edit_lines(text, [4], "o/y@L1", "o/y@L2")
    assert out.splitlines()[3] == "      - uses: o/y@L2 # v1"
