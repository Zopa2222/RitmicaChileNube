import { Routes } from '@angular/router';
import { ChampionshipsListComponent } from './features/championships-list/championships-list.component';
import { SetupComponent } from './features/setup/setup.component';
import { ScoringComponent } from './features/scoring/scoring.component';
import { ExportComponent } from './features/export/export.component';
import {
    PublicResultsComponent
} from './features/public-results/public-results.component';
import { LoginComponent } from './features/login/login.component';
import { PortalComponent } from './features/portal/portal.component';
import {
    AccessDeniedComponent
} from './features/access-denied/access-denied.component';
import {
    ChampionshipDetailComponent
} from './features/championship-detail/championship-detail.component';
import { OperationsComponent } from './features/operations/operations.component';
import { CloudScoringComponent } from './features/cloud-scoring/cloud-scoring.component';
import { JudgeCabinComponent } from './features/judge-cabin/judge-cabin.component';
import { CloudAdministrationComponent } from './features/cloud-administration/cloud-administration.component';
import { CloudExportComponent } from './features/cloud-export/cloud-export.component';
import {
    authGuard,
    guestGuard,
    roleGuard
} from './core/auth/auth.guards';

const ADMIN_ROLES = ['SUPER_ADMIN', 'GLOBAL_ADMIN'] as const;

export const routes: Routes = [
    { path: '', component: PublicResultsComponent },
    { path: 'resultados', redirectTo: '', pathMatch: 'full' },
    {
        path: 'ingresar',
        component: LoginComponent,
        canActivate: [guestGuard]
    },
    {
        path: 'administracion',
        component: PortalComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'superadministracion',
        redirectTo: 'superadministracion/configuracion',
        pathMatch: 'full'
    },
    {
        path: 'superadministracion/configuracion',
        component: CloudAdministrationComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ['SUPER_ADMIN'], section: 'configuration' }
    },
    {
        path: 'superadministracion/jueces',
        component: CloudAdministrationComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ['SUPER_ADMIN'], section: 'judges' }
    },
    {
        path: 'cabina-juez',
        component: JudgeCabinComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ['JUDGE'] }
    },
    {
        path: 'championships',
        component: ChampionshipsListComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'championships/:championshipId/import',
        component: SetupComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'championships/:championshipId/operations',
        component: OperationsComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'championships/:championshipId/categories/:categoryId/scoring',
        component: CloudScoringComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'championships/:championshipId/export',
        component: CloudExportComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'championships/:championshipId',
        component: ChampionshipDetailComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'setup',
        component: SetupComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'scoring',
        component: ScoringComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'export',
        component: ExportComponent,
        canActivate: [authGuard, roleGuard],
        data: { roles: ADMIN_ROLES }
    },
    {
        path: 'sin-permiso',
        component: AccessDeniedComponent,
        canActivate: [authGuard]
    },
    { path: '**', redirectTo: '/' }
];
