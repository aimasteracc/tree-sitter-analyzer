// JavaScript class test

class Animal {
    constructor(name) {
        this.name = name;
    }

    speak() {
        console.log(`${this.name} makes a sound`);
    }
}

class Dog extends Animal {
    constructor(name, breed) {
        super(name);
        this.breed = breed;
    }

    speak() {
        console.log(`${this.name} barks`);
    }

    getBreed() {
        return this.breed;
    }
}

// Export test
export class Cat extends Animal {
    constructor(name) {
        super(name);
    }

    speak() {
        console.log(`${this.name} meows`);
    }
}
