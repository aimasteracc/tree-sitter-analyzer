"""Built-in PHP corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
<?php
declare(strict_types=1);
namespace App\\Controllers;
use App\\Models\\User;
use App\\Services\\UserService;

const MAX_ITEMS = 100;

interface Repository {
    public function find(int $id): ?User;
    public function findAll(): array;
}

#[\\Attribute(\\Attribute::TARGET_CLASS)]
class Controller {
    public function __construct(public readonly string $prefix = "") {}
}

#[Controller(prefix: "/users")]
class UserController {
    public function __construct(
        private readonly UserService $service,
        private readonly int $maxItems = MAX_ITEMS
    ) {}

    public function show(int $id): ?User { return $this->service->find($id); }
    public static function create(UserService $s): static { return new static($s); }

    public function controlFlow(int $x): void {
        if ($x > 0) { } elseif ($x < 0) { } else { }
        for ($i = 0; $i < $x; $i++) { if ($i==3) continue; if ($i==7) break; }
        foreach ($this->service->findAll() as $item) { }
        while ($x > 0) { $x--; }
        do { $x++; } while ($x < 5);
        switch ($x) { case 1: break; default: break; }
        label_a: goto label_a;
        try { throw new \\Exception(); }
        catch (\\Exception $e) { } finally { }
        echo "hello";
        exit(0);
        unset($x);
        global $globalVar;
        static $staticVar = 0;
        ;
        use \\Some\\Namespace\\ClassName;
    }

    public function funcDef(): void { function inner() {} }
}

trait Timestampable {
    private \\DateTimeImmutable $createdAt;
    public function getCreatedAt(): \\DateTimeImmutable { return $this->createdAt; }
}

class WithTraits {
    use Timestampable;
}

enum Status: string {
    case Active = "active";
    case Inactive = "inactive";
    public function label(): string {
        return match($this) { Status::Active => "Active", default => "Inactive" };
    }
}

$items = array_filter(array_map(fn($x) => $x * 2, range(1, 10)), fn($x) => $x > 10);
"""
