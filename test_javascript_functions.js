function getValue() {
    return "test";
}

function setValue(value) {
    this.value = value;
}

const createList = (item) => {
    return [item];
}

class TestClass {
    constructor(value) {
        this.value = value;
    }
    
    isValid(input, strict) {
        return input != null && input.length > 0;
    }
}