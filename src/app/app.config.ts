import {
    APP_INITIALIZER,
    ApplicationConfig,
    LOCALE_ID,
    provideZoneChangeDetection
} from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeEsCl from '@angular/common/locales/es-CL';
import { provideRouter } from '@angular/router';
import {
    provideHttpClient,
    withInterceptors
} from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';

import { routes } from './app.routes';
import { cloudAuthInterceptor } from './core/auth/auth.interceptor';
import { AuthService } from './core/auth/auth.service';

registerLocaleData(localeEsCl);

function restoreSession(authService: AuthService): () => Promise<void> {
    return () => authService.restoreSession();
}

export const appConfig: ApplicationConfig = {
    providers: [
        provideZoneChangeDetection({ eventCoalescing: true }),
        provideRouter(routes),
        provideHttpClient(withInterceptors([cloudAuthInterceptor])),
        provideAnimations(),
        {
            provide: APP_INITIALIZER,
            useFactory: restoreSession,
            deps: [AuthService],
            multi: true
        },
        { provide: LOCALE_ID, useValue: 'es-CL' }
    ]
};
