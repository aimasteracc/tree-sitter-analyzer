public class TestAnnotation {

    @Override
    public String toString() {
        return "test";
    }

    @Test
    public void testMethod() {
        // test code
    }

    @SuppressWarnings("unchecked")
    @Deprecated
    public void multiAnnotationMethod() {
        // deprecated code
    }

    public void regularMethod() {
        // no annotation
    }
}
