"""Small Pygame renderer for an authoritative square; no local physics."""

import math
import uuid

import pygame


class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.dx = self.dy = self.angle = 0
        self.size = 24
        self.id = str(uuid.uuid4())
        self.team = 1
        self.local = False

    def set_position(self, x, y):
        self.x, self.y = x, y

    def set_rotation(self, angle):
        self.angle = angle

    def set_velocity(self, dx, dy):
        self.dx, self.dy = dx, dy

    def move(self):
        self.x += self.dx
        self.y += self.dy

    def draw(self, screen):
        fill = (32, 35, 31) if self.team == 1 else (250, 250, 245)
        stroke = (250, 250, 245) if self.team == 1 else (32, 35, 31)

        def corners(half):
            c, s = math.cos(self.angle), math.sin(self.angle)
            return [
                (self.x + x * c - y * s, self.y + x * s + y * c)
                for x, y in [(-half, -half), (half, -half), (half, half), (-half, half)]
            ]

        pygame.draw.polygon(screen, fill, corners(self.size / 2))
        pygame.draw.polygon(screen, stroke, corners(self.size / 2), 2)
        if self.local:
            pygame.draw.polygon(screen, (32, 35, 31), corners(17), 6)
            pygame.draw.polygon(screen, (255, 56, 105), corners(17), 3)
            label = pygame.font.Font(None, 22).render("YOU", True, (255, 56, 105), (32, 35, 31))
            screen.blit(label, (max(0, min(1160, self.x - 18)), max(0, self.y - 40)))
