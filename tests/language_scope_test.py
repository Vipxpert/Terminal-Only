# /llm_harness/tests/language_scope_test.py
"""Language-scope test for llm_harness: definitions and their blocks are found in C#, Java, Kotlin, Rust, C and C++ (modifiers, constructors, Allman braces, attributes), calls, conditions and Python, JS and Go statements are not mistaken for definitions, and the existing forms still work."""
import importlib.util, os, sys

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


CSHARP = """namespace Game
{
    [Serializable]
    public class Player : MonoBehaviour
    {
        [SerializeField] private int health;

        public Player(int hp)
        {
            health = hp;
        }

        [Obsolete("use Heal")]
        public async Task<int> Heal(int amount)
        {
            await Task.Delay(1);
            return amount;
        }

        private static void Log(string s) => Console.WriteLine(s);
    }
}""".split("\n")


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    name = lambda line: (hh.def_info(line) or (None,))[0]
    cases = (
        ("C# class", "    public class Player : MonoBehaviour", "Player"),
        ("C# namespace", "namespace Game", "Game"),
        ("C# constructor", "        public Player(int hp)", "Player"),
        ("C# async generic method", "        public async Task<int> Heal(int amount)", "Heal"),
        ("C# expression-bodied method", "        private static void Log(string s) => Console.WriteLine(s);", "Log"),
        ("C# override", "        public override string ToString()", "ToString"),
        ("Java main", "    public static void main(String[] args) {", "main"),
        ("Java package-private method", "    void run() {", "run"),
        ("Java method with throws", "    public int read() throws IOException {", "read"),
        ("Java record", "public record Point(int x, int y) {", "Point"),
        ("Kotlin fun", "fun main() {", "main"),
        ("Kotlin override fun", "    override fun toString(): String {", "toString"),
        ("Kotlin extension fun", "fun String.shout() = uppercase()", "shout"),
        ("Kotlin data class", "data class Point(val x: Int)", "Point"),
        ("Kotlin object", "object Config {", "Config"),
        ("Rust async fn", "    pub async fn run(&self) -> Result<()> {", "run"),
        ("Rust impl", "impl Player {", "Player"),
        ("Rust mod", "mod tests {", "tests"),
        ("C++ function in column 0", "int main(int argc, char** argv)", "main"),
        ("C++ method of a class", "void Player::Heal(int a) const {", "Heal"),
        ("C static function", "static int helper(int v) {", "helper"),
        ("C struct", "struct Node {", "Node"),
    )
    bad = [(label, line, name(line), want) for label, line, want in cases if name(line) != want]
    check("definitions are found in C#, Java, Kotlin, Rust, C and C++", not bad, bad)
    nots = (
        "            await Task.Delay(1);", "            return amount;", "            health = hp;", "        [SerializeField] private int health;",
        "        if (x) {", "        } else if (y) {", "        for (int i = 0; i < n; i++) {", "        catch (Exception e) {", "        while (a) {", "        synchronized (this) {",
        "        new Thread(() -> {", "        return foo(bar);", "        throw new Foo(x);", "    printf(\"hi\");", "    std::cout << foo(x) << \"\\n\";",
        "    x = foo(a)", "    assert foo(x)", "    if a and foo(b):", "    a and foo(b)", "    print(foo(x))", "    return foo(a)", "const x = foo(a)", "export default connect(mapState)(Foo)",
        "    x := foo(a)", "    go foo(x)", "    defer foo()", "let y = foo(1);",
    )
    wrong = [(s, name(s)) for s in nots if name(s)]
    check("calls, conditions and statements are not mistaken for definitions", not wrong, wrong)
    old = (("def foo(a, b):", "foo"), ("class A:", "A"), ("    async def run(self):", "run"), ("func (s *Server) Start() error {", "Start"), ("  render() {", "render"), ("  async fetchData(id) {", "fetchData"), ("const f = (a) => a", "f"), ("export function load() {", "load"))
    check("Python, Go and JS definitions are found as before", all(name(l) == w for l, w in old), [(l, name(l)) for l, w in old if name(l) != w])
    heal = next(i for i, l in enumerate(CSHARP) if "Heal(int amount)" in l)
    lo, hi = hh.block_bounds(CSHARP, heal, False)
    body = CSHARP[lo:hi]
    check("a C# method's block runs from its attribute to its closing brace, Allman braces included", body[0].strip().startswith("[Obsolete") and body[-1].strip() == "}" and any("Task.Delay" in l for l in body) and not any("Log(" in l for l in body), body)
    ctor = next(i for i, l in enumerate(CSHARP) if "public Player(int hp)" in l)
    lo, hi = hh.block_bounds(CSHARP, ctor, False)
    check("a constructor's block does not swallow the method after it", any("health = hp" in l for l in CSHARP[lo:hi]) and not any("Heal" in l for l in CSHARP[lo:hi]), CSHARP[lo:hi])
    cls = next(i for i, l in enumerate(CSHARP) if "public class Player" in l)
    lo, hi = hh.block_bounds(CSHARP, cls, False)
    check("a class block starts at its attribute and ends at its closing brace", CSHARP[lo].strip() == "[Serializable]" and CSHARP[hi - 1].strip() == "}" and any("Log(" in l for l in CSHARP[lo:hi]), CSHARP[lo:hi][:3])
    check("the source files of these languages are scanned for @XREF and the Unused probe", all(e in hh.CODE_EXTS for e in (".cs", ".java", ".kt", ".rs", ".cpp", ".h", ".swift")))
    unity = (("    void Start()", "Start"), ("    void Update()", "Update"), ("    void OnTriggerEnter2D(Collider2D collision)", "OnTriggerEnter2D"), ("    private void Awake()", "Awake"), ("    IEnumerator Fade(float t)", "Fade"), ("    List<int> Items()", "Items"), ("    public IActionResult Get([FromQuery] int id)", "Get"), ("    public void Run(Dictionary<string, int> map, int n = 3)", "Run"), ("object Config {", "Config"), ("record Point(int x, int y) {", "Point"), ("mod tests;", "tests"))
    missed = [(l, name(l), w) for l, w in unity if name(l) != w]
    check("Unity-style methods with no modifier and the brace on the next line are found", not missed, missed)
    prose = ("headers: module headers install location (posix_local is /local/ prefixed)", "    Return a tuple (low, high) where low and high are", "    WARNING: It would be disastrous to call run_until_complete()", "    year, month, day (required, base 1)", "    Returns None (see below)", "object is then obtained by calling opener with (*name*, *flags*).", "record to it.", "extension module development.", "STAT                    stat()", "float constructor (for example, '-2.3' or '1e10')", "object types: modules, functions, classes,")
    wrong = [(s, name(s)) for s in prose if name(s)]
    check("prose lines in docstrings and comments are not mistaken for definitions", not wrong, wrong)
    snippet = "class A : MonoBehaviour\n{\n    void Start()\n    {\n        x = 1;\n    }\n\n    void Update()\n    {\n        y = 2;\n    }\n}".split("\n")
    start = next(i for i, l in enumerate(snippet) if "void Start()" in l)
    lo, hi = hh.block_bounds(snippet, start, False)
    check("a modifier-less Allman method's block ends at its own closing brace", any("x = 1" in l for l in snippet[lo:hi]) and not any("y = 2" in l for l in snippet[lo:hi]), snippet[lo:hi])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
