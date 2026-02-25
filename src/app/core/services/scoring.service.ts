import { Injectable } from '@angular/core';
import { Gymnast } from '../models/gymnast.model';
import { Judge, getJudgeDisplayName } from '../models/judge.model';

export interface ScoreValidation {
    hasError: boolean;
    errorColumns: string[]; // Columns with >0.6 difference
}

@Injectable({
    providedIn: 'root'
})
export class ScoringService {

    /**
     * Calculate total score for a gymnast
     */
    calculateTotalScore(gymnast: Gymnast, judges: Judge[]): number {
        let total = 0;

        // Add DA and DB scores directly
        const daScore = gymnast.scores['DA'] || 0;
        const dbScore = gymnast.scores['DB'] || 0;
        total += daScore + dbScore;

        // Calculate E score
        const eJudges = judges.filter(j => j.role === 'E');
        const eScore = this.calculateAreaScore(gymnast, eJudges, 'E');
        total += eScore;

        // Calculate A score
        const aJudges = judges.filter(j => j.role === 'A');
        const aScore = this.calculateAreaScore(gymnast, aJudges, 'A');
        total += aScore;

        // Subtract Desc
        total -= (gymnast.desc || 0);

        return Math.max(0, total); // Score cannot be negative
    }

    /**
     * Calculate score for E or A area
     * Rules:
     * - 1 judge: 10 - score
     * - 2-3 judges: 10 - average(all scores)
     * - 4 judges: 10 - average(exclude min and max)
     */
    private calculateAreaScore(gymnast: Gymnast, judges: Judge[], area: 'E' | 'A'): number {
        if (judges.length === 0) return 0;

        const scores: number[] = [];
        judges.forEach(judge => {
            const key = getJudgeDisplayName(judge);
            const score = gymnast.scores[key];
            if (score !== undefined && score !== null) {
                scores.push(score);
            }
        });

        if (scores.length === 0) return 0;

        let deduction = 0;

        if (scores.length === 1) {
            // 1 judge: 10 - score
            deduction = scores[0];
        } else if (scores.length === 2 || scores.length === 3) {
            // 2-3 judges: average all
            deduction = scores.reduce((sum, s) => sum + s, 0) / scores.length;
        } else if (scores.length >= 4) {
            // 4+ judges: exclude min and max, then average
            const sorted = [...scores].sort((a, b) => a - b);
            const middle = sorted.slice(1, -1);
            deduction = middle.reduce((sum, s) => sum + s, 0) / middle.length;
        }

        return 10 - deduction;
    }

    /**
     * Validate scores and check for differences > 0.6 in E and A areas
     */
    validateScores(gymnast: Gymnast, judges: Judge[]): ScoreValidation {
        const errorColumns: string[] = [];

        // Check E judges
        const eJudges = judges.filter(j => j.role === 'E');
        if (eJudges.length >= 2) {
            const hasEError = this.checkAreaDifference(gymnast, eJudges);
            if (hasEError) {
                eJudges.forEach(j => errorColumns.push(getJudgeDisplayName(j)));
            }
        }

        // Check A judges
        const aJudges = judges.filter(j => j.role === 'A');
        if (aJudges.length >= 2) {
            const hasAError = this.checkAreaDifference(gymnast, aJudges);
            if (hasAError) {
                aJudges.forEach(j => errorColumns.push(getJudgeDisplayName(j)));
            }
        }

        return {
            hasError: errorColumns.length > 0,
            errorColumns
        };
    }

    /**
     * Check if difference between judges in same area exceeds 0.6
     */
    private checkAreaDifference(gymnast: Gymnast, judges: Judge[]): boolean {
        const scores: number[] = [];

        judges.forEach(judge => {
            const key = getJudgeDisplayName(judge);
            const score = gymnast.scores[key];
            if (score !== undefined && score !== null) {
                scores.push(score);
            }
        });

        if (scores.length < 2) return false;

        const min = Math.min(...scores);
        const max = Math.max(...scores);

        return (max - min) > 0.6;
    }

    /**
     * Get all score column names based on judges
     */
    getScoreColumns(judges: Judge[]): string[] {
        const columns: string[] = [];

        // Add DA and DB
        if (judges.some(j => j.role === 'DA')) columns.push('DA');
        if (judges.some(j => j.role === 'DB')) columns.push('DB');

        // Add E judges
        const eJudges = judges.filter(j => j.role === 'E').sort((a, b) => (a.index || 0) - (b.index || 0));
        eJudges.forEach(j => columns.push(getJudgeDisplayName(j)));

        // Add A judges
        const aJudges = judges.filter(j => j.role === 'A').sort((a, b) => (a.index || 0) - (b.index || 0));
        aJudges.forEach(j => columns.push(getJudgeDisplayName(j)));

        // Add L if exists
        if (judges.some(j => j.role === 'L')) columns.push('L');

        return columns;
    }
}
