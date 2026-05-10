import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from env import load_dotenv


class DotenvLoadingTest(unittest.TestCase):
    def test_loads_values_from_cwd_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "OPENAI_API_KEY=test-key\nOPENAI_MODEL=test-model\nSESSION_ROOT=/tmp/sessions\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                    load_dotenv()

                self.assertEqual(os.environ["OPENAI_API_KEY"], "test-key")
                self.assertEqual(os.environ["OPENAI_MODEL"], "test-model")
                self.assertEqual(os.environ["SESSION_ROOT"], "/tmp/sessions")

    def test_existing_environment_values_are_not_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "shell-key"}, clear=True):
                with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                    load_dotenv()

                self.assertEqual(os.environ["OPENAI_API_KEY"], "shell-key")


if __name__ == "__main__":
    unittest.main()
