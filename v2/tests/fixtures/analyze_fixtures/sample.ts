/**
 * Sample TypeScript file for analyze tool testing.
 */

export interface User {
    id: number;
    name: string;
    email: string;
}

export class UserService {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    findById(id: number): User | undefined {
        return this.users.find(u => u.id === id);
    }
}

export function formatUser(user: User): string {
    return `${user.name} <${user.email}>`;
}
