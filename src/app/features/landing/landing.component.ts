import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [MatCardModule, MatButtonModule, MatIconModule],
  templateUrl: './landing.component.html',
  styleUrls: ['./landing.component.scss']
})
export class LandingComponent {
  constructor(private router: Router) { }

  createNewChampionship(): void {
    this.router.navigate(['/setup']);
  }

  viewChampionships(): void {
    this.router.navigate(['/championships']);
  }

  viewFinalists(): void {
    this.router.navigate(['/finalistas']);
  }
}
