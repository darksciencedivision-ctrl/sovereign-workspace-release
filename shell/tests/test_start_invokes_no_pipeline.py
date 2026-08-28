"""G47: distillery start path invokes no pipeline entry point."""
import ast, os, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(WS, "modules", "distillery", "serve.py")

class TestStartInvokesNoPipeline(unittest.TestCase):
    def test_serve_imports_no_pipeline(self):
        with open(SRC, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        mods = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods.extend(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module:
                mods.append(n.module)
        banned = [m for m in mods if any(x in m.lower() for x in ("train", "pipeline", "distill", "merge"))]
        self.assertEqual(banned, [])
        self.assertTrue(any("http.server" in m for m in mods))

if __name__ == "__main__":
    unittest.main()
