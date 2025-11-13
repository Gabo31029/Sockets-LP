-- Script SQL para crear la base de datos y tablas del sistema de chat
-- Ejecutar: mysql -u root -p < schema.sql

-- Crear la base de datos si no existe
CREATE DATABASE IF NOT EXISTS chat_app;

-- Usar la base de datos
USE chat_app;

-- Tabla de usuarios
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL
);

