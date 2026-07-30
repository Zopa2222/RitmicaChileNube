export type AccountType = 'SUPER_ADMIN' | 'GLOBAL_ADMIN' | 'JUDGE';

export interface AuthenticatedUser {
    id: string;
    username: string;
    first_name: string;
    last_name: string;
    account_type: AccountType;
}

export interface LoginCredentials {
    username: string;
    password: string;
}

export interface AuthResponse {
    user: AuthenticatedUser;
}

export interface JudgeAccessWindow {
    championship_id: string;
    competition_day_id: string;
    starts_at: string;
    ends_at: string;
}

export function homeRouteForAccountType(accountType: AccountType): string {
    switch (accountType) {
        case 'SUPER_ADMIN':
            return '/superadministracion';
        case 'GLOBAL_ADMIN':
            return '/administracion';
        case 'JUDGE':
            return '/cabina-juez';
    }
}

export function accountTypeLabel(accountType: AccountType): string {
    switch (accountType) {
        case 'SUPER_ADMIN':
            return 'Superadministrador';
        case 'GLOBAL_ADMIN':
            return 'Administrador global';
        case 'JUDGE':
            return 'Juez';
    }
}
