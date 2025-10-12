public class TestClass {
    public String getValue() {
        return "test";
    }
    
    public void setValue(int value) {
        this.value = value;
    }
    
    public static <T> List<T> createList(T item) {
        return Arrays.asList(item);
    }
    
    public TestClass(int value) {
        this.value = value;
    }
    
    private boolean isValid(String input, boolean strict) {
        return input != null && !input.isEmpty();
    }
}