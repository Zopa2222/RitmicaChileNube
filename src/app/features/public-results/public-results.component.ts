import { CommonModule } from '@angular/common';
import {
    Component,
    DestroyRef,
    OnInit,
    inject
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import {
    Subject,
    catchError,
    debounceTime,
    distinctUntilChanged,
    of,
    startWith,
    switchMap,
    tap
} from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
    PublicCatalogResponse,
    PublicCategoryResultsResponse,
    PublicCategorySummary,
    PublicLiveGymnast,
    PublicSortMode
} from '../../core/models/public-results.model';
import {
    PublicResultsService
} from '../../core/services/public-results.service';
import { AuthService } from '../../core/auth/auth.service';

@Component({
    selector: 'app-public-results',
    standalone: true,
    imports: [
        CommonModule,
        MatButtonModule,
        MatIconModule,
        ReactiveFormsModule,
        RouterLink
    ],
    templateUrl: './public-results.component.html',
    styleUrls: ['./public-results.component.scss']
})
export class PublicResultsComponent implements OnInit {
    private readonly destroyRef = inject(DestroyRef);
    private readonly catalogRequests = new Subject<string>();
    private resultRequestToken = 0;

    readonly searchControl = new FormControl('', { nonNullable: true });
    readonly user$ = this.authService.user$;

    catalog: PublicCatalogResponse | null = null;
    categories: PublicCategorySummary[] = [];
    selectedCategory: PublicCategorySummary | null = null;
    categoryResults: PublicCategoryResultsResponse | null = null;
    sortMode: PublicSortMode = 'passing_order';
    loadingCatalog = true;
    loadingResults = false;
    noActiveChampionship = false;
    errorMessage = '';
    liveNavigationMessage = '';
    selectedLiveGymnastId: string | null = null;
    private pendingLiveGymnastId: string | null = null;

    constructor(
        private readonly publicResultsService: PublicResultsService,
        private readonly authService: AuthService
    ) { }

    ngOnInit(): void {
        this.catalogRequests.pipe(
            tap(() => {
                this.loadingCatalog = true;
                this.errorMessage = '';
                this.noActiveChampionship = false;
            }),
            switchMap(query => this.publicResultsService
                .getActiveChampionship(query)
                .pipe(
                    catchError((error: HttpErrorResponse) => {
                        this.handleCatalogError(error);
                        return of(null);
                    })
                )
            ),
            takeUntilDestroyed(this.destroyRef)
        ).subscribe(response => {
            this.loadingCatalog = false;
            if (response) {
                this.applyCatalog(response);
            }
        });

        this.searchControl.valueChanges.pipe(
            startWith(this.searchControl.value),
            debounceTime(250),
            distinctUntilChanged(),
            takeUntilDestroyed(this.destroyRef)
        ).subscribe(query => this.catalogRequests.next(query));
    }

    selectCategory(category: PublicCategorySummary): void {
        if (this.selectedCategory?.id === category.id) {
            return;
        }
        this.selectedCategory = category;
        this.selectedLiveGymnastId = null;
        this.loadSelectedCategory();
    }

    viewLive(gymnast: PublicLiveGymnast): void {
        if (!gymnast?.gymnast_id || !gymnast.category_id) {
            this.liveNavigationMessage =
                'No hay una gimnasta disponible para mostrar en vivo.';
            return;
        }
        if (!this.catalog) {
            this.liveNavigationMessage =
                'No hay un campeonato activo para consultar.';
            return;
        }

        this.liveNavigationMessage = '';
        this.pendingLiveGymnastId = gymnast.gymnast_id;
        this.selectedLiveGymnastId = gymnast.gymnast_id;
        this.searchControl.setValue('', { emitEvent: false });
        this.catalogRequests.next('');
    }

    changeSort(event: Event): void {
        this.sortMode = (
            event.target as HTMLSelectElement
        ).value as PublicSortMode;
        this.loadSelectedCategory();
    }

    refresh(): void {
        this.catalogRequests.next(this.searchControl.value);
    }

    clearSearch(): void {
        this.searchControl.setValue('');
    }

    categoryTrackBy(
        _index: number,
        category: PublicCategorySummary
    ): string {
        return category.id;
    }

    resultTrackBy(
        _index: number,
        result: { gymnast_id: string }
    ): string {
        return result.gymnast_id;
    }

    private applyCatalog(response: PublicCatalogResponse): void {
        this.catalog = response;
        this.categories = response.categories;
        const previousId = this.selectedCategory?.id;
        this.selectedCategory = (
            this.categories.find(category => (
                category.id === this.pendingLiveCategoryId()
            ))
            ?? this.categories.find(category => category.id === previousId)
            ?? this.categories[0]
            ?? null
        );
        if (this.selectedCategory) {
            this.loadSelectedCategory();
        } else {
            this.categoryResults = null;
            this.loadingResults = false;
            if (this.pendingLiveGymnastId) {
                this.pendingLiveGymnastId = null;
                this.selectedLiveGymnastId = null;
                this.liveNavigationMessage =
                    'La gimnasta en vivo ya no está asociada a una categoría disponible.';
            }
        }
    }

    private loadSelectedCategory(): void {
        if (!this.selectedCategory) {
            return;
        }
        const requestToken = ++this.resultRequestToken;
        this.loadingResults = true;
        this.errorMessage = '';
        this.publicResultsService.getCategoryResults(
            this.selectedCategory.id,
            this.sortMode,
            this.searchControl.value
        ).pipe(
            takeUntilDestroyed(this.destroyRef)
        ).subscribe({
            next: response => {
                if (requestToken !== this.resultRequestToken) {
                    return;
                }
                this.categoryResults = response;
                this.loadingResults = false;
                this.scrollToPendingLiveGymnast(response);
            },
            error: () => {
                if (requestToken !== this.resultRequestToken) {
                    return;
                }
                this.categoryResults = null;
                this.loadingResults = false;
                this.errorMessage =
                    'No fue posible cargar los resultados de la categoría.';
            }
        });
    }

    private handleCatalogError(error: HttpErrorResponse): void {
        this.catalog = null;
        this.categories = [];
        this.selectedCategory = null;
        this.categoryResults = null;
        this.pendingLiveGymnastId = null;
        this.selectedLiveGymnastId = null;
        this.loadingResults = false;
        if (
            error.status === 404
            && error.error?.code === 'ACTIVE_CHAMPIONSHIP_NOT_FOUND'
        ) {
            this.noActiveChampionship = true;
            return;
        }
        this.errorMessage =
            'No fue posible consultar los resultados públicos.';
    }

    private pendingLiveCategoryId(): string | null {
        if (!this.pendingLiveGymnastId) {
            return null;
        }
        return this.catalog?.live_gymnasts?.find(
            gymnast => gymnast.gymnast_id === this.pendingLiveGymnastId
        )?.category_id ?? null;
    }

    private scrollToPendingLiveGymnast(
        response: PublicCategoryResultsResponse
    ): void {
        const gymnastId = this.pendingLiveGymnastId;
        if (!gymnastId) {
            return;
        }
        if (response.category.id !== this.selectedCategory?.id) {
            return;
        }
        const isInResults = response.results.some(
            result => result.gymnast_id === gymnastId
        );
        this.pendingLiveGymnastId = null;
        if (!isInResults) {
            this.selectedLiveGymnastId = null;
            this.liveNavigationMessage =
                'La gimnasta ya no está disponible en los resultados. Actualiza para consultar el estado en vivo.';
            return;
        }
        window.setTimeout(() => {
            document.getElementById(`live-gymnast-${gymnastId}`)
                ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    }
}
