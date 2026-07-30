import { inject } from '@angular/core';
import {
    CanActivateFn,
    Router
} from '@angular/router';

import {
    AccountType,
    homeRouteForAccountType
} from '../models/auth.model';
import { AuthStateService } from './auth-state.service';

export const authGuard: CanActivateFn = (_route, state) => {
    const authState = inject(AuthStateService);
    const router = inject(Router);

    return authState.user
        ? true
        : router.createUrlTree(['/ingresar'], {
            queryParams: { returnUrl: state.url }
        });
};

export const roleGuard: CanActivateFn = (route, state) => {
    const authState = inject(AuthStateService);
    const router = inject(Router);
    const user = authState.user;

    if (!user) {
        return router.createUrlTree(['/ingresar'], {
            queryParams: { returnUrl: state.url }
        });
    }

    const allowedRoles =
        (route.data['roles'] as readonly AccountType[] | undefined) ?? [];
    if (allowedRoles.length === 0 || allowedRoles.includes(user.account_type)) {
        return true;
    }

    return router.createUrlTree(['/sin-permiso'], {
        queryParams: {
            home: homeRouteForAccountType(user.account_type)
        }
    });
};

export const guestGuard: CanActivateFn = () => {
    const authState = inject(AuthStateService);
    const router = inject(Router);

    return authState.user
        ? router.createUrlTree([
            homeRouteForAccountType(authState.user.account_type)
        ])
        : true;
};
