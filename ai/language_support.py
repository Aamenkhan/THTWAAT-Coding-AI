"""
ai/language_support.py — Multi-language Support (Feature 14)
Optimized prompts and context for 12 programming languages.
Detects language from file extension and adjusts AI behaviour.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class LanguageProfile:
    name: str
    extensions: List[str]
    comment_style: str         # e.g. '#', '//', '/* */'
    test_command: str          # e.g. 'pytest', 'npm test'
    lint_command: str          # e.g. 'ruff', 'eslint'
    formatter: str             # e.g. 'black', 'prettier'
    package_manager: str       # e.g. 'pip', 'npm'
    entry_points: List[str]    # common main files
    style_guide: str           # e.g. 'PEP8', 'Airbnb'
    idioms: List[str] = field(default_factory=list)


LANGUAGES: Dict[str, LanguageProfile] = {
    "python": LanguageProfile(
        name="Python", extensions=[".py", ".pyw"],
        comment_style="#", test_command="pytest",
        lint_command="ruff check .", formatter="black",
        package_manager="pip", entry_points=["main.py", "app.py", "__main__.py"],
        style_guide="PEP 8",
        idioms=["Use dataclasses", "Prefer f-strings", "Use pathlib", "Type hints everywhere"],
    ),
    "javascript": LanguageProfile(
        name="JavaScript", extensions=[".js", ".mjs", ".cjs"],
        comment_style="//", test_command="npm test",
        lint_command="eslint .", formatter="prettier",
        package_manager="npm", entry_points=["index.js", "app.js", "server.js"],
        style_guide="Airbnb",
        idioms=["Use const/let not var", "Arrow functions", "Async/await", "Destructuring"],
    ),
    "typescript": LanguageProfile(
        name="TypeScript", extensions=[".ts", ".tsx"],
        comment_style="//", test_command="npx jest",
        lint_command="eslint . --ext .ts", formatter="prettier",
        package_manager="npm", entry_points=["index.ts", "main.ts", "app.ts"],
        style_guide="TypeScript strict",
        idioms=["Explicit types", "Interfaces over types", "Generics", "Strict null checks"],
    ),
    "react": LanguageProfile(
        name="React", extensions=[".jsx", ".tsx"],
        comment_style="//", test_command="npx jest",
        lint_command="eslint . --ext .jsx,.tsx", formatter="prettier",
        package_manager="npm", entry_points=["App.jsx", "App.tsx", "index.jsx"],
        style_guide="React best practices",
        idioms=["Functional components", "Hooks over class", "Props destructuring", "useCallback/useMemo"],
    ),
    "nextjs": LanguageProfile(
        name="Next.js", extensions=[".tsx", ".ts", ".jsx", ".js"],
        comment_style="//", test_command="npx jest",
        lint_command="next lint", formatter="prettier",
        package_manager="npm", entry_points=["pages/index.tsx", "app/page.tsx"],
        style_guide="Next.js conventions",
        idioms=["Server components", "App router", "API routes", "getServerSideProps"],
    ),
    "nodejs": LanguageProfile(
        name="Node.js", extensions=[".js", ".mjs"],
        comment_style="//", test_command="npm test",
        lint_command="eslint .", formatter="prettier",
        package_manager="npm", entry_points=["server.js", "app.js", "index.js"],
        style_guide="Node.js best practices",
        idioms=["ES modules", "Async/await", "Express middleware", "Event emitters"],
    ),
    "java": LanguageProfile(
        name="Java", extensions=[".java"],
        comment_style="//", test_command="mvn test",
        lint_command="checkstyle", formatter="google-java-format",
        package_manager="maven", entry_points=["Main.java", "Application.java"],
        style_guide="Google Java Style",
        idioms=["SOLID principles", "Builder pattern", "Optional", "Stream API"],
    ),
    "csharp": LanguageProfile(
        name="C#", extensions=[".cs"],
        comment_style="//", test_command="dotnet test",
        lint_command="dotnet format --verify-no-changes", formatter="dotnet format",
        package_manager="nuget", entry_points=["Program.cs", "Startup.cs"],
        style_guide="Microsoft C# coding conventions",
        idioms=["LINQ", "async/await", "Records", "Nullable reference types"],
    ),
    "go": LanguageProfile(
        name="Go", extensions=[".go"],
        comment_style="//", test_command="go test ./...",
        lint_command="golangci-lint run", formatter="gofmt",
        package_manager="go modules", entry_points=["main.go", "cmd/main.go"],
        style_guide="Effective Go",
        idioms=["Error as values", "Goroutines", "Interfaces", "Table-driven tests"],
    ),
    "rust": LanguageProfile(
        name="Rust", extensions=[".rs"],
        comment_style="//", test_command="cargo test",
        lint_command="cargo clippy", formatter="cargo fmt",
        package_manager="cargo", entry_points=["src/main.rs", "src/lib.rs"],
        style_guide="Rust API Guidelines",
        idioms=["Ownership/borrowing", "Result/Option", "Traits", "Pattern matching"],
    ),
    "php": LanguageProfile(
        name="PHP", extensions=[".php"],
        comment_style="//", test_command="phpunit",
        lint_command="phpstan analyse", formatter="php-cs-fixer",
        package_manager="composer", entry_points=["index.php", "app/index.php"],
        style_guide="PSR-12",
        idioms=["Typed properties", "Named arguments", "Match expressions", "Fibers"],
    ),
    "flutter": LanguageProfile(
        name="Flutter/Dart", extensions=[".dart"],
        comment_style="//", test_command="flutter test",
        lint_command="dart analyze", formatter="dart format",
        package_manager="pub", entry_points=["lib/main.dart"],
        style_guide="Dart style guide",
        idioms=["Widgets", "Provider/Riverpod", "Async/Future", "Null safety"],
    ),
}

# Extension → language key lookup
_EXT_MAP: Dict[str, str] = {}
for _key, _profile in LANGUAGES.items():
    for _ext in _profile.extensions:
        if _ext not in _EXT_MAP:
            _EXT_MAP[_ext] = _key


class LanguageSupport:
    """Detect language and generate optimized prompts/context."""

    @staticmethod
    def detect(path: str) -> Optional[LanguageProfile]:
        """Detect language from file extension."""
        ext = Path(path).suffix.lower()
        key = _EXT_MAP.get(ext)
        return LANGUAGES.get(key) if key else None

    @staticmethod
    def detect_project(directory: str) -> Optional[LanguageProfile]:
        """Detect primary language of a project by file count."""
        counts: Dict[str, int] = {}
        for p in Path(directory).rglob("*"):
            if p.is_file():
                key = _EXT_MAP.get(p.suffix.lower())
                if key:
                    counts[key] = counts.get(key, 0) + 1
        if not counts:
            return None
        primary = max(counts, key=counts.get)
        return LANGUAGES.get(primary)

    @staticmethod
    def build_system_prompt(profile: LanguageProfile) -> str:
        """Build a language-optimized system prompt prefix."""
        idioms_text = "\n".join(f"  - {i}" for i in profile.idioms)
        return (
            f"You are an expert {profile.name} developer.\n"
            f"Style guide: {profile.style_guide}\n"
            f"Package manager: {profile.package_manager}\n"
            f"Test runner: {profile.test_command}\n"
            f"Formatter: {profile.formatter}\n"
            f"Language idioms to follow:\n{idioms_text}\n"
            "Generate production-quality, fully implemented code.\n"
            "Follow SOLID principles. No placeholder code. No TODO comments.\n"
        )

    @staticmethod
    def get_test_command(directory: str) -> str:
        """Auto-detect the test command for a project."""
        profile = LanguageSupport.detect_project(directory)
        return profile.test_command if profile else "echo 'No test runner detected'"

    @staticmethod
    def get_lint_command(directory: str) -> str:
        """Auto-detect the lint command for a project."""
        profile = LanguageSupport.detect_project(directory)
        return profile.lint_command if profile else "echo 'No linter detected'"

    @staticmethod
    def all_supported() -> List[str]:
        return [p.name for p in LANGUAGES.values()]
