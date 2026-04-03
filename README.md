# VisionX - Lawrence Vision Sync Engine

VisionX is a high-performance data synchronization engine designed to bridge legacy Lawrence Vision systems with modern data infrastructure. It gathers production line data from multiple legacy MySQL/MariaDB databases and exports it to a target MariaDB instance and an InfluxDB time-series database for real-time monitoring and analytics.

## Purpose

The primary goal of VisionX is to provide a reliable, automated pipeline to:
- Access legacy Windows XP-based Vision systems.
- Gather production line data (weights, piece counts, speeds, etc.).
- Normalize timestamps (using source time or host-time overrides).
- Export data to a centralized target database.
- Stream metrics to InfluxDB for visualization on dashboards.

## Features

- **Multi-Source Support**: Synchronize multiple production lines concurrently.
- **Time Handling**: Toggle between using source database time or local host time for accurate historical tracking.
- **Interactive Management**: A user-friendly CLI tool for configuration and deployment.
- **Dockerized Architecture**: Easy to deploy and scale using Docker Compose.
- **Real-Time Dashboard**: Includes a built-in React-based dashboard for monitoring sync status and performance.

## Prerequisites

- Docker
- Docker Compose

## Quick Start

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/visionx.git
    cd visionx
    ```

2.  **Make the deployment script executable**:
    ```bash
    chmod +x deploy.sh
    ```

3.  **Run the interactive setup**:
    ```bash
    ./deploy.sh
    ```
    Follow the prompts to configure your source databases, target database, and InfluxDB settings.

    > [!IMPORTANT]
    > **Database Permissions**: The credentials provided for the target database must have temporary permissions to **CREATE** tables during the initialization step. Once the tables are created, only **INSERT** and **UPDATE** permissions are required for normal operation.

4.  **Create Tables**:
    From the management menu in `deploy.sh`, select **5) Create Tables (Target DB)** to initialize the required schema.

5.  **Launch the system**:
    From the main menu in `deploy.sh`, select **2) Launch**.

## Deployment Commands

The `deploy.sh` script provides several management capabilities:
- **configure**: Interactively set up or modify environment variables.
- **launch**: Build and start the services in detached mode.
- **stop**: Stop running services.
- **remove**: Tear down containers and networks.
- **update**: Pull the latest code and restart services.

## Project Structure

- `app/`: Python sync engine and API.
- `ui/`: React-based monitoring dashboard.
- `docker-compose.yml`: Docker service orchestration.
- `deploy.sh`: Primary management tool.
- `.env.sample`: Template for environment configuration.

## License

[MIT](LICENSE)
