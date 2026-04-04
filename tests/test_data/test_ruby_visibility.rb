# Test Ruby visibility modifiers extraction

class TestVisibility
  # Default is public
  def public_method
    puts "I'm public"
  end

  # attr_accessor default public
  attr_accessor :public_attr

  # Switch to private
  private

  def private_method1
    puts "I'm private"
  end

  def private_method2
    puts "Also private"
  end

  # attr_reader under private
  attr_reader :private_attr

  # Switch to protected
  protected

  def protected_method
    puts "I'm protected"
  end

  # attr_writer under protected
  attr_writer :protected_attr

  # Switch back to public
  public

  def another_public_method
    puts "Back to public"
  end
end

class NestedVisibility
  # Nested class should have independent visibility state
  def public_in_nested
    puts "public in nested"
  end

  private

  def private_in_nested
    puts "private in nested"
  end
end
