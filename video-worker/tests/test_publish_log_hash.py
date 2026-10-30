from app.publish_log import file_sha256


def test_file_sha256_changes_with_content(tmp_path):
    a = tmp_path / "a.mp4"
    a.write_bytes(b"FIRST")
    b = tmp_path / "b.mp4"
    b.write_bytes(b"SECOND")

    assert file_sha256(str(a)) == file_sha256(str(a))
    assert file_sha256(str(a)) != file_sha256(str(b))


def test_file_sha256_reads_whole_file_beyond_chunk(tmp_path):
    """Kısaltma değil, içeriğin tamamı özetlenir (chunk sınırı 1 MiB)."""
    small = tmp_path / "small.mp4"
    small.write_bytes(b"A" * 100)
    large = tmp_path / "large.mp4"
    large.write_bytes(b"A" * (3 << 20))

    assert file_sha256(str(small)) != file_sha256(str(large))
