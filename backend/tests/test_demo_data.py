import subprocess
import sys


def test_generator_is_reproducible_and_does_not_overwrite(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    command = [sys.executable, "-m", "app.demo_data", "--count", "12", "--seed", "42"]
    subprocess.run([*command, "--output", str(first)], check=True)
    subprocess.run([*command, "--output", str(second)], check=True)
    assert first.read_bytes() == second.read_bytes()
    assert "模拟" in first.read_text(encoding="utf-8-sig")
    result = subprocess.run([*command, "--output", str(first)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "已存在" in result.stderr
