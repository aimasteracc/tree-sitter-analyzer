// Sample Java file in nested directory

public class Sample {
    private String name;

    public Sample(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }

    public void sayHello() {
        System.out.println("Hello from " + name);
    }
}
