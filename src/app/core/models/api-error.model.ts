import { JudgeAccessWindow } from './auth.model';

export interface ApiErrorBody {
    error: string;
    code: string;
    next_access_window?: JudgeAccessWindow | null;
}
