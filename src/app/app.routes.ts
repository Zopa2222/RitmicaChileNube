import { Routes } from '@angular/router';
import { LandingComponent } from './features/landing/landing.component';
import { ChampionshipsListComponent } from './features/championships-list/championships-list.component';
import { SetupComponent } from './features/setup/setup.component';
import { ScoringComponent } from './features/scoring/scoring.component';
import { ExportComponent } from './features/export/export.component';
import { FinalistsComponent } from './features/finalists/finalists.component';

export const routes: Routes = [
    { path: '', component: LandingComponent },
    { path: 'championships', component: ChampionshipsListComponent },
    { path: 'setup', component: SetupComponent },
    { path: 'scoring', component: ScoringComponent },
    { path: 'export', component: ExportComponent },
    { path: 'finalistas', component: FinalistsComponent },
    { path: '**', redirectTo: '/' }
];
