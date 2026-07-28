# Stage 1: Build Angular application
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the Angular application
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

# Remove default nginx index.html
RUN rm -rf /usr/share/nginx/html/*

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built application from builder stage
# Angular 17 creates a browser subdirectory, copy its contents
COPY --from=builder /app/dist/gymnastics-scoring/browser /usr/share/nginx/html/

# Expose port (mapped from 4200)
EXPOSE 4200

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:4200/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
