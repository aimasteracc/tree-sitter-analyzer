// Sample TypeScript file for search testing

interface User {
  name: string;
  email: string;
}

function greetUser(user: User): string {
  return `Hello, ${user.name}!`;
}

export class UserManager {
  private users: User[] = [];

  addUser(user: User): void {
    this.users.push(user);
  }

  findUserByEmail(email: string): User | undefined {
    return this.users.find(u => u.email === email);
  }
}
