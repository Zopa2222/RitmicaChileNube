import { BancaJudge } from './judge.model';
import { Category } from './category.model';

// Championship interface
export interface Championship {
    id?: string;
    name: string;
    bancaA: BancaJudge[];
    bancaB: BancaJudge[];
    categoriasBanca: { [catName: string]: 'A' | 'B' };
    categories: Category[];
    createdAt?: Date;
}

// Create empty championship
export function createEmptyChampionship(): Championship {
    return {
        name: '',
        bancaA: [],
        bancaB: [],
        categoriasBanca: {},
        categories: []
    };
}
