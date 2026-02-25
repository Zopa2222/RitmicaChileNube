import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Championship } from '../models/championship.model';
import { Category } from '../models/category.model';
import { Judge } from '../models/judge.model';

@Injectable({
    providedIn: 'root'
})
export class ChampionshipService {
    private championshipSubject = new BehaviorSubject<Championship | null>(null);
    public championship$: Observable<Championship | null> = this.championshipSubject.asObservable();

    private currentCategorySubject = new BehaviorSubject<Category | null>(null);
    public currentCategory$: Observable<Category | null> = this.currentCategorySubject.asObservable();

    /**
     * Set current championship
     */
    setChampionship(championship: Championship): void {
        this.championshipSubject.next(championship);
    }

    /**
     * Get current championship
     */
    getChampionship(): Championship | null {
        return this.championshipSubject.value;
    }

    /**
     * Update championship data
     */
    updateChampionship(updates: Partial<Championship>): void {
        const current = this.championshipSubject.value;
        if (current) {
            this.championshipSubject.next({ ...current, ...updates });
        }
    }

    /**
     * Set current category being edited
     */
    setCurrentCategory(category: Category): void {
        this.currentCategorySubject.next(category);
    }

    /**
     * Get current category
     */
    getCurrentCategory(): Category | null {
        return this.currentCategorySubject.value;
    }

    /**
     * Update current category
     */
    updateCurrentCategory(updates: Partial<Category>): void {
        const current = this.currentCategorySubject.value;
        if (current) {
            this.currentCategorySubject.next({ ...current, ...updates });
        }
    }

    /**
     * Get judges from current championship
     */
    getJudges(): Judge[] {
        return this.championshipSubject.value?.judges || [];
    }

    /**
     * Clear all state
     */
    clear(): void {
        this.championshipSubject.next(null);
        this.currentCategorySubject.next(null);
    }
}
