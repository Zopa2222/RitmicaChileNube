import { Judge } from './judge.model';
import { Category } from './category.model';

// Championship interface
export interface Championship {
    id?: string;
    name: string;
    judges: Judge[];
    categories: Category[];
    createdAt?: Date;
}

// Create empty championship
export function createEmptyChampionship(): Championship {
    return {
        name: '',
        judges: [],
        categories: []
    };
}
