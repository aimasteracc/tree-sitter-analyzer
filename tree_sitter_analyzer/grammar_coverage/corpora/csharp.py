"""Built-in C# corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

// Top-level statements (C# 9+ global_statement)
Console.WriteLine("global statement");
int topLevel = 42;

namespace Example;

[AttributeUsage(AttributeTargets.Class)]
public class ServiceAttribute : Attribute { public string Name { get; init; } = ""; }

public interface IRepository<T> where T : class {
    Task<T?> FindAsync(int id);
    Task<IEnumerable<T>> FindAllAsync();
}

public record Point(double X, double Y);
public enum Status { Active, Inactive, Pending }

public delegate void EventHandler(object sender, EventArgs e);

public struct ValuePoint { public int X, Y; }

[Service(Name = "UserService")]
public class UserService : IRepository<User>
{
    private readonly List<User> _users = [];
    public event EventHandler? Changed;
    public event EventHandler MyEvent { add { } remove { } }

    public async Task<User?> FindAsync(int id) {
        await Task.Delay(0);
        return _users.FirstOrDefault(u => u.Id == id);
    }

    public async Task<IEnumerable<User>> FindAllAsync() {
        await Task.Delay(0);
        return _users.AsEnumerable();
    }

    ~UserService() { }

    public int this[int index] { get => _users[index].Id; }

    public void ControlFlow(int x) {
        if (x > 0) { } else if (x < 0) { } else { }
        for (int i = 0; i < x; i++) { if (i==3) continue; if (i==7) break; }
        foreach (var u in _users) { }
        while (x > 0) { x--; }
        do { x++; } while (x < 5);
        switch (x) { case 1: break; default: break; }
        label: goto label;
        try { throw new Exception(); }
        catch (ArgumentException e) when (e != null) { }
        catch (Exception) { }
        finally { }
        checked { int y = x + 1; }
        unsafe { int* p = &x; }
        lock (this) { }
        using var res = new System.IO.MemoryStream();
        fixed (char* p = "hello") { }
        int result = x switch { 1 => 1, _ => 0 };
        yield return x;
        yield break;
        int local = 0;
        void LocalFn() { local++; }
        LocalFn();
    }

}

namespace Example.Sub
{
    public class SubClass
    {
        public SubClass() { }

        public event EventHandler? MyEvent;

        public void GlobalAndUsing()
        {
            ;
            using var r = new System.IO.MemoryStream();
            using (var r2 = new System.IO.MemoryStream()) { }
        }
    }

    global using System.Collections.Generic;
}

public class User
{
    public int Id { get; set; }
    public required string Name { get; set; }
    public string? Email { get; set; }
    public override string ToString() => $"User({Id}, {Name})";
}
"""
