<?php
/**
 * PHP Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-php grammar
 * to verify complete coverage of PHP language features.
 *
 * Coverage includes:
 * - Function definitions (regular, anonymous, arrow)
 * - Class declarations (regular, abstract, final)
 * - Interface declarations
 * - Trait declarations
 * - Method declarations (public, private, protected, static, abstract)
 * - Property declarations
 * - Namespace definitions
 * - Use declarations
 * - Const declarations
 * - Anonymous function creation expressions
 */

// ============================================================================
// NAMESPACE DEFINITIONS
// ============================================================================

namespace GoldenCorpus\Models;

use GoldenCorpus\Interfaces\Animal;
use GoldenCorpus\Traits\Describable;
use function GoldenCorpus\Helpers\format_name;
use const GoldenCorpus\Constants\MAX_AGE;

// ============================================================================
// INTERFACE DECLARATIONS
// ============================================================================

/**
 * Basic interface
 */
interface Animal {
    public function makeSound(): string;
    public function getAge(): int;
}

/**
 * Interface with constants
 */
interface Configurable {
    public const VERSION = '1.0.0';
    public const MAX_RETRY = 3;

    public function configure(array $options): void;
}

/**
 * Interface extending other interface
 */
interface Domesticated extends Animal {
    public function getOwner(): string;
}

// ============================================================================
// TRAIT DECLARATIONS
// ============================================================================

/**
 * Basic trait
 */
trait Describable {
    protected string $description = '';

    public function describe(): string {
        return $this->description ?: 'No description';
    }

    public function setDescription(string $desc): void {
        $this->description = $desc;
    }
}

/**
 * Trait with abstract methods
 */
trait Trackable {
    protected int $createdAt;

    abstract protected function getId(): int;

    public function track(): void {
        $this->createdAt = time();
    }

    public function getCreatedAt(): int {
        return $this->createdAt;
    }
}

/**
 * Trait using other traits
 */
trait FullyDescribable {
    use Describable;
    use Trackable;

    public function fullDescription(): string {
        return sprintf(
            '[ID: %d] %s (created: %s)',
            $this->getId(),
            $this->describe(),
            date('Y-m-d', $this->getCreatedAt())
        );
    }
}

// ============================================================================
// CLASS DECLARATIONS - REGULAR
// ============================================================================

/**
 * Regular class with various property types
 */
class Person implements Animal {
    // Public property declaration
    public string $name;
    public int $age;

    // Protected property declaration
    protected ?string $email = null;

    // Private property declaration
    private array $metadata = [];

    // Static property declaration
    public static int $instanceCount = 0;

    // Typed property with default value
    private bool $isActive = true;

    // Constructor (method declaration)
    public function __construct(string $name, int $age) {
        $this->name = $name;
        $this->age = $age;
        self::$instanceCount++;
    }

    // Public method declaration
    public function greet(): string {
        return sprintf("Hello, I'm %s and I'm %d years old", $this->name, $this->age);
    }

    // Protected method declaration
    protected function validate(): bool {
        return $this->age >= 0 && $this->age <= 150;
    }

    // Private method declaration
    private function formatMetadata(): string {
        return json_encode($this->metadata);
    }

    // Static method declaration
    public static function getInstanceCount(): int {
        return self::$instanceCount;
    }

    // Method with type hints and return type
    public function setEmail(?string $email): self {
        $this->email = $email;
        return $this;
    }

    // Method with default parameters
    public function updateAge(int $increment = 1): void {
        $this->age += $increment;
    }

    // Interface implementation
    public function makeSound(): string {
        return "Hello!";
    }

    public function getAge(): int {
        return $this->age;
    }

    // Destructor
    public function __destruct() {
        self::$instanceCount--;
    }

    // Magic methods
    public function __toString(): string {
        return $this->greet();
    }

    public function __get(string $name) {
        return $this->metadata[$name] ?? null;
    }

    public function __set(string $name, $value): void {
        $this->metadata[$name] = $value;
    }
}

// ============================================================================
// CLASS DECLARATIONS - ABSTRACT
// ============================================================================

/**
 * Abstract class
 */
abstract class AbstractShape {
    protected string $color;

    public function __construct(string $color) {
        $this->color = $color;
    }

    // Abstract method declaration
    abstract public function getArea(): float;
    abstract protected function getPerimeter(): float;

    // Concrete method in abstract class
    public function getColor(): string {
        return $this->color;
    }
}

/**
 * Class extending abstract class
 */
class Circle extends AbstractShape {
    private float $radius;

    public function __construct(string $color, float $radius) {
        parent::__construct($color);
        $this->radius = $radius;
    }

    public function getArea(): float {
        return pi() * $this->radius ** 2;
    }

    protected function getPerimeter(): float {
        return 2 * pi() * $this->radius;
    }
}

// ============================================================================
// CLASS DECLARATIONS - FINAL
// ============================================================================

/**
 * Final class (cannot be extended)
 */
final class ImmutablePoint {
    public function __construct(
        public readonly float $x,
        public readonly float $y,
        public readonly float $z = 0.0
    ) {}

    public function distance(): float {
        return sqrt($this->x ** 2 + $this->y ** 2 + $this->z ** 2);
    }
}

// ============================================================================
// CLASS WITH TRAITS
// ============================================================================

class Product {
    use Describable;
    use Trackable {
        track as protected;
    }

    private int $id;
    private string $name;
    private float $price;

    public function __construct(int $id, string $name, float $price) {
        $this->id = $id;
        $this->name = $name;
        $this->price = $price;
    }

    protected function getId(): int {
        return $this->id;
    }

    public function getPrice(): float {
        return $this->price;
    }
}

// ============================================================================
// ANONYMOUS CLASSES
// ============================================================================

function anonymousClassExample(): object {
    return new class implements Animal {
        private string $sound = "Anonymous sound";

        public function makeSound(): string {
            return $this->sound;
        }

        public function getAge(): int {
            return 0;
        }
    };
}

// ============================================================================
// FUNCTION DEFINITIONS
// ============================================================================

/**
 * Regular function definition
 */
function regularFunction(int $a, int $b): int {
    return $a + $b;
}

/**
 * Function with default parameters
 */
function functionWithDefaults(string $name, int $age = 18, ?string $email = null): array {
    return compact('name', 'age', 'email');
}

/**
 * Function with variadic parameters
 */
function variadicFunction(string $separator, string ...$parts): string {
    return implode($separator, $parts);
}

/**
 * Function with reference parameters
 */
function swapValues(int &$a, int &$b): void {
    $temp = $a;
    $a = $b;
    $b = $temp;
}

/**
 * Function with union types (PHP 8.0+)
 */
function processValue(int|float|string $value): string {
    return (string) $value;
}

/**
 * Function with mixed return type
 */
function getMixedValue(string $key): mixed {
    $data = ['key1' => 42, 'key2' => 'string', 'key3' => [1, 2, 3]];
    return $data[$key] ?? null;
}

/**
 * Function returning array with specific shape
 */
function getUserData(int $userId): array {
    return [
        'id' => $userId,
        'name' => 'User ' . $userId,
        'active' => true,
    ];
}

// ============================================================================
// ANONYMOUS FUNCTION CREATION EXPRESSIONS (Closures)
// ============================================================================

function closureExamples(): void {
    // Simple anonymous function
    $add = function(int $a, int $b): int {
        return $a + $b;
    };

    // Anonymous function with use clause
    $multiplier = 10;
    $multiply = function(int $x) use ($multiplier): int {
        return $x * $multiplier;
    };

    // Anonymous function with reference in use clause
    $counter = 0;
    $increment = function() use (&$counter): void {
        $counter++;
    };

    // Anonymous function as callback
    $numbers = [1, 2, 3, 4, 5];
    $doubled = array_map(function($n) {
        return $n * 2;
    }, $numbers);

    // Anonymous function with multiple use variables
    $prefix = "Item: ";
    $suffix = " units";
    $formatter = function(int $value) use ($prefix, $suffix): string {
        return $prefix . $value . $suffix;
    };
}

// ============================================================================
// ARROW FUNCTIONS (PHP 7.4+)
// ============================================================================

function arrowFunctionExamples(): void {
    // Simple arrow function
    $square = fn(int $x): int => $x * $x;

    // Arrow function with implicit variable capture
    $multiplier = 5;
    $multiply = fn(int $x): int => $x * $multiplier;

    // Arrow function as array_map callback
    $numbers = [1, 2, 3, 4, 5];
    $squared = array_map(fn($n) => $n ** 2, $numbers);

    // Arrow function with multiple parameters
    $add = fn(int $a, int $b): int => $a + $b;

    // Nested arrow functions
    $makeAdder = fn(int $x): callable => fn(int $y): int => $x + $y;
}

// ============================================================================
// CONST DECLARATIONS
// ============================================================================

// Global const declaration
const GLOBAL_CONSTANT = 'global value';
const MAX_RETRIES = 3;
const PI_VALUE = 3.14159;

// Class constants (already shown in interfaces/classes above)

// ============================================================================
// NAMESPACE AND USE EXAMPLES
// ============================================================================

namespace GoldenCorpus\Services;

use GoldenCorpus\Models\Person;
use GoldenCorpus\Models\Product;
use GoldenCorpus\Models\Circle;

class ServiceClass {
    public function createPerson(string $name, int $age): Person {
        return new Person($name, $age);
    }

    public function createProduct(int $id, string $name, float $price): Product {
        return new Product($id, $name, $price);
    }
}

// ============================================================================
// GLOBAL NAMESPACE
// ============================================================================

namespace {
    // Back to global namespace

    /**
     * Global function
     */
    function globalHelper(string $message): void {
        echo $message . PHP_EOL;
    }

    // ============================================================================
    // STATIC METHODS AND PROPERTIES
    // ============================================================================

    class StaticExample {
        public static int $staticCounter = 0;
        private static array $cache = [];

        public static function increment(): void {
            self::$staticCounter++;
        }

        public static function getCounter(): int {
            return self::$staticCounter;
        }

        public static function cache(string $key, mixed $value): void {
            self::$cache[$key] = $value;
        }

        public static function getCached(string $key): mixed {
            return self::$cache[$key] ?? null;
        }
    }

    // ============================================================================
    // FIRST-CLASS CALLABLE SYNTAX (PHP 8.1+)
    // ============================================================================

    function firstClassCallableExamples(): void {
        // First-class callable from function
        $callback = regularFunction(...);

        // First-class callable from method
        $person = new GoldenCorpus\Models\Person('Alice', 30);
        $greetCallback = $person->greet(...);

        // First-class callable from static method
        $staticCallback = StaticExample::getCounter(...);
    }

    // ============================================================================
    // GENERATORS (yield)
    // ============================================================================

    function generatorFunction(int $max): Generator {
        for ($i = 0; $i < $max; $i++) {
            yield $i;
        }
    }

    function generatorWithKeys(array $data): Generator {
        foreach ($data as $key => $value) {
            yield $key => $value;
        }
    }

    function generatorYieldFrom(array $arrays): Generator {
        foreach ($arrays as $array) {
            yield from $array;
        }
    }

    // ============================================================================
    // CONSTRUCTOR PROPERTY PROMOTION (PHP 8.0+)
    // ============================================================================

    class PromotedConstructor {
        public function __construct(
            public string $name,
            protected int $age,
            private array $data = []
        ) {}
    }

    // ============================================================================
    // ENUMS (PHP 8.1+)
    // ============================================================================

    enum Status {
        case PENDING;
        case ACTIVE;
        case INACTIVE;
    }

    enum StatusCode: int {
        case SUCCESS = 200;
        case NOT_FOUND = 404;
        case SERVER_ERROR = 500;

        public function message(): string {
            return match($this) {
                self::SUCCESS => 'Success',
                self::NOT_FOUND => 'Not Found',
                self::SERVER_ERROR => 'Server Error',
            };
        }
    }

    // ============================================================================
    // MAIN EXECUTION
    // ============================================================================

    // Create instances and test functionality
    $person = new GoldenCorpus\Models\Person('Bob', 25);
    echo $person->greet() . PHP_EOL;

    $circle = new GoldenCorpus\Models\Circle('red', 5.0);
    echo "Circle area: " . $circle->getArea() . PHP_EOL;

    $point = new ImmutablePoint(3.0, 4.0);
    echo "Point distance: " . $point->distance() . PHP_EOL;

    // Test closures
    closureExamples();

    // Test arrow functions
    arrowFunctionExamples();

    // Test static methods
    StaticExample::increment();
    echo "Static counter: " . StaticExample::getCounter() . PHP_EOL;

    // Test generators
    foreach (generatorFunction(5) as $value) {
        echo $value . " ";
    }
    echo PHP_EOL;
}
