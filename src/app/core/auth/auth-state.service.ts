import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

import {
    AccountType,
    AuthenticatedUser
} from '../models/auth.model';

@Injectable({ providedIn: 'root' })
export class AuthStateService {
    private readonly userSubject =
        new BehaviorSubject<AuthenticatedUser | null>(null);

    readonly user$ = this.userSubject.asObservable();

    get user(): AuthenticatedUser | null {
        return this.userSubject.value;
    }

    setUser(user: AuthenticatedUser): void {
        this.userSubject.next(user);
    }

    clear(): void {
        this.userSubject.next(null);
    }

    hasAnyRole(roles: readonly AccountType[]): boolean {
        return this.user !== null && roles.includes(this.user.account_type);
    }
}
