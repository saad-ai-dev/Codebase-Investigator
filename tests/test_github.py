import unittest

from github import GitHubUrlError, parse_github_url


class ParseGitHubUrlTest(unittest.TestCase):
    def test_parses_repository_root(self) -> None:
        ref = parse_github_url("https://github.com/openai/openai-python")
        self.assertEqual(ref.owner, "openai")
        self.assertEqual(ref.repo, "openai-python")
        self.assertIsNone(ref.ref)
        self.assertIsNone(ref.subpath)

    def test_parses_tree_url(self) -> None:
        ref = parse_github_url("https://github.com/openai/openai-python/tree/main/src/openai")
        self.assertEqual(ref.ref, "main")
        self.assertEqual(ref.subpath, "src/openai")

    def test_parses_blob_url(self) -> None:
        ref = parse_github_url("https://github.com/openai/openai-python/blob/main/README.md")
        self.assertEqual(ref.ref, "main")
        self.assertEqual(ref.subpath, "README.md")

    def test_rejects_non_github_url(self) -> None:
        with self.assertRaises(GitHubUrlError):
            parse_github_url("https://example.com/not-github")


if __name__ == "__main__":
    unittest.main()
