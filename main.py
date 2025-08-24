import pygame
import sys
from dataclasses import dataclass
from collections import deque

# ------------ Settings ------------
TILE = 24
GRID_W = 26
GRID_H = 26
SCREEN_W = GRID_W * TILE
SCREEN_H = GRID_H * TILE
FPS = 60

# Colors
COLOR_BG = (16, 16, 20)
COLOR_GRID = (28, 28, 34)
COLOR_BRICK = (200, 80, 50)
COLOR_STEEL = (145, 145, 155)
COLOR_WATER = (55, 115, 205)
COLOR_BUSH  = (44, 120, 60)
COLOR_PLAYER = (240, 200, 60)
COLOR_ENEMY  = (225, 85, 85)
COLOR_BULLET = (245, 245, 245)
COLOR_EAGLE  = (220, 220, 30)
COLOR_TEXT   = (235, 235, 235)
COLOR_UI_ACCENT = (255, 200, 80)

STATE_MENU = 0
STATE_PLAYING = 1
STATE_GAMEOVER = 2
STATE_VICTORY = 3

def clamp(n, a, b):
    return max(a, min(b, n))

def draw_subtle_grid(screen):
    for x in range(0, SCREEN_W, TILE):
        pygame.draw.line(screen, COLOR_GRID, (x, 0), (x, SCREEN_H))
    for y in range(0, SCREEN_H, TILE):
        pygame.draw.line(screen, COLOR_GRID, (0, y), (SCREEN_W, y))

# ------------ Tiles ------------
class Tile(pygame.sprite.Sprite):
    def __init__(self, pos, color, solid=True, destructible=False, name="tile"):
        super().__init__()
        self.image = pygame.Surface((TILE, TILE))
        self.image.fill(color)
        self.rect = self.image.get_rect(topleft=pos)
        self.solid = solid
        self.destructible = destructible
        self.name = name

class Brick(Tile):
    def __init__(self, pos):
        super().__init__(pos, COLOR_BRICK, solid=True, destructible=True, name="brick")

class Steel(Tile):
    def __init__(self, pos):
        super().__init__(pos, COLOR_STEEL, solid=True, destructible=False, name="steel")

class Water(Tile):
    def __init__(self, pos):
        super().__init__(pos, COLOR_WATER, solid=True, destructible=False, name="water")

class Bush(Tile):
    def __init__(self, pos):
        super().__init__(pos, COLOR_BUSH, solid=False, destructible=False, name="bush")
        self.image.set_alpha(210)

class Eagle(Tile):
    def __init__(self, pos):
        super().__init__(pos, COLOR_EAGLE, solid=True, destructible=True, name="eagle")
        pygame.draw.rect(self.image, (90, 90, 30), self.image.get_rect(), 2)

# ------------ Bullet ------------
class Bullet(pygame.sprite.Sprite):
    def __init__(self, pos, direction, speed=6, owner=None):
        super().__init__()
        self.image = pygame.Surface((8, 8))
        self.image.fill(COLOR_BULLET)
        self.rect = self.image.get_rect(center=pos)
        self.dir = pygame.Vector2(direction)
        self.speed = speed
        self.owner = owner

    def update(self, game):
        self.rect.x += int(self.dir.x * self.speed)
        self.rect.y += int(self.dir.y * self.speed)

        # bounds
        if not (0 <= self.rect.centerx < SCREEN_W and 0 <= self.rect.centery < SCREEN_H):
            self.kill(); return

        # tiles
        hit_tiles = pygame.sprite.spritecollide(self, game.solid_tiles, False)
        if hit_tiles:
            for t in hit_tiles:
                if t.destructible:
                    t.kill()
                    if t.name == "eagle":
                        game.state = STATE_GAMEOVER
                        game.state_reason = "Your base was destroyed!"
            self.kill(); return

        # tanks
        target = game.enemies if self.owner and self.owner.is_player else game.players
        hit_tanks = pygame.sprite.spritecollide(self, target, False)
        if hit_tanks:
            for tank in hit_tanks:
                tank.take_hit(game)
            self.kill()

# ------------ Tank ------------
class Tank(pygame.sprite.Sprite):
    def __init__(self, pos, color, is_player=False, speed=2.2):
        super().__init__()
        self.base_image = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        self.base_image.fill(color)
        pygame.draw.rect(self.base_image, (0,0,0), self.base_image.get_rect(), 2)
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect(topleft=pos)
        self.dir = pygame.Vector2(0, -1)
        self.speed = speed
        self.is_player = is_player
        self.bullet_cooldown = 350
        self._last_shot = 0
        self.invuln_until = 0

    def bbox_move(self, game, dx, dy):
        self.rect.x += dx
        hits = pygame.sprite.spritecollide(self, game.blocking_tiles, False)
        for h in hits:
            if dx > 0: self.rect.right = h.rect.left
            elif dx < 0: self.rect.left = h.rect.right

        self.rect.y += dy
        hits = pygame.sprite.spritecollide(self, game.blocking_tiles, False)
        for h in hits:
            if dy > 0: self.rect.bottom = h.rect.top
            elif dy < 0: self.rect.top = h.rect.bottom

        self.rect.left = clamp(self.rect.left, 0, SCREEN_W - self.rect.width)
        self.rect.top = clamp(self.rect.top, 0, SCREEN_H - self.rect.height)

    def shoot(self, game):
        now = pygame.time.get_ticks()
        if now - self._last_shot < self.bullet_cooldown: return
        active = sum(1 for b in game.bullets if b.owner is self)
        if active >= 1: return
        self._last_shot = now
        tip = self.get_barrel_tip()
        b = Bullet(tip, self.dir, speed=7 if self.is_player else 6, owner=self)
        game.all_sprites.add(b); game.bullets.add(b)
        if self.is_player: game.player_bullets.add(b)
        else: game.enemy_bullets.add(b)

    def get_barrel_tip(self):
        cx, cy = self.rect.center
        if self.dir.x == 0 and self.dir.y == -1: return (cx, self.rect.top - 2)
        elif self.dir.x == 0 and self.dir.y == 1: return (cx, self.rect.bottom + 2)
        elif self.dir.x == -1 and self.dir.y == 0: return (self.rect.left - 2, cy)
        else: return (self.rect.right + 2, cy)

    def take_hit(self, game):
        if pygame.time.get_ticks() < self.invuln_until: return
        if self.is_player:
            game.player_lives -= 1
            if game.player_lives >= 0:
                game.respawn_player()
            else:
                game.state = STATE_GAMEOVER
                game.state_reason = "You ran out of lives."
        else:
            self.kill()

    def update(self, game): pass

class PlayerTank(Tank):
    def __init__(self, pos):
        super().__init__(pos, COLOR_PLAYER, is_player=True, speed=2.6)

    def update(self, game):
        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx = -self.speed; self.dir = pygame.Vector2(-1, 0)
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx = self.speed; self.dir = pygame.Vector2(1, 0)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy = -self.speed; self.dir = pygame.Vector2(0, -1) if dx == 0 else self.dir
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy = self.speed; self.dir = pygame.Vector2(0, 1) if dx == 0 else self.dir
        if dx != 0 and dy != 0: dy = 0
        self.bbox_move(game, int(dx), int(dy))

class EnemyTank(Tank):
    def __init__(self, pos):
        super().__init__(pos, COLOR_ENEMY, is_player=False, speed=1.9)
        self.ai_next_plan = 0
        self.path = []  # list of grid cells to follow

    def update(self, game):
        now = pygame.time.get_ticks()
        # Re-plan path every ~700ms or if path empty
        if now > self.ai_next_plan or not self.path:
            self.ai_next_plan = now + 700
            self.path = bfs_path_to_player(game, self)

        # Follow the path (grid to direction)
        if self.path:
            # target next cell center
            cell = self.path[0]
            tx = cell[0]*TILE + TILE//2
            ty = cell[1]*TILE + TILE//2
            vx = tx - self.rect.centerx
            vy = ty - self.rect.centery
            if abs(vx) > abs(vy):
                self.dir = pygame.Vector2(1 if vx>0 else -1, 0)
            else:
                self.dir = pygame.Vector2(0, 1 if vy>0 else -1)
            # If close to center, pop step
            if abs(vx) <= 2 and abs(vy) <= 2:
                self.path.pop(0)

        # move and shoot
        self.bbox_move(game, int(self.dir.x * self.speed), int(self.dir.y * self.speed))

        # occasional firing
        if now % 600 < 20:
            self.shoot(game)

# ------------ Level ------------
@dataclass
class LevelData:
    player_spawn: pygame.Vector2 | None
    enemy_spawns: list
    eagle: object | None

class Level:
    def __init__(self, path): self.path = path

    def load(self, game):
        with open(self.path, "r", encoding="utf-8") as f:
            rows = [line.rstrip("\n") for line in f.readlines() if line.strip("\n")]
        if len(rows) != GRID_H or any(len(r) != GRID_W for r in rows):
            raise ValueError("Level must be 26x26 characters.")
        player_spawn, enemy_spawns, eagle_obj = None, [], None
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                pos = (x*TILE, y*TILE)
                if ch == ".": pass
                elif ch == "B": game.add_tile(Brick(pos))
                elif ch == "S": game.add_tile(Steel(pos))
                elif ch == "W": game.add_tile(Water(pos))
                elif ch == "H": game.add_overlay(Bush(pos))
                elif ch == "E":
                    eagle = Eagle(pos); game.add_tile(eagle); eagle_obj = eagle
                elif ch == "P": player_spawn = pygame.Vector2(pos)
                elif ch == "X": enemy_spawns.append(pygame.Vector2(pos))
        return LevelData(player_spawn, enemy_spawns, eagle_obj)

# ------------ Pathfinding (BFS) ------------
def cell_blocked(game, cx, cy):
    if not (0 <= cx < GRID_W and 0 <= cy < GRID_H): return True
    rect = pygame.Rect(cx*TILE, cy*TILE, TILE, TILE)
    for t in game.blocking_tiles:
        if rect.colliderect(t.rect): return True
    return False

def bfs_path(game, start, goal):
    """Return list of (cx,cy) from after start to goal (excluding start) using BFS grid search."""
    if start == goal: return []
    q = deque([start])
    came = {start: None}
    while q:
        cur = q.popleft()
        if cur == goal: break
        x,y = cur
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = x+dx, y+dy
            nxt = (nx, ny)
            if nxt in came: continue
            if cell_blocked(game, nx, ny): continue
            came[nxt] = cur
            q.append(nxt)
    if goal not in came: return []
    # Reconstruct
    path = []
    cur = goal
    while cur != start:
        path.append(cur)
        cur = came[cur]
    path.reverse()
    return path

def bfs_path_to_player(game, enemy):
    if not game.player: return []
    scx, scy = enemy.rect.centerx // TILE, enemy.rect.centery // TILE
    gcx, gcy = game.player.rect.centerx // TILE, game.player.rect.centery // TILE
    start = (int(scx), int(scy)); goal = (int(gcx), int(gcy))
    # Temporarily ignore the enemy's own cell blockage by moving it out of collision set (approx via rect move)
    return bfs_path(game, start, goal)

# ------------ Game ------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Battle City — Python Starter")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 20, bold=True)
        self.big = pygame.font.SysFont("Consolas", 32, bold=True)

        self.state = STATE_MENU
        self.state_reason = ""

        self.setup_world()

    def setup_world(self):
        # groups
        self.all_sprites = pygame.sprite.Group()
        self.players = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()
        self.player_bullets = pygame.sprite.Group()
        self.enemy_bullets = pygame.sprite.Group()
        self.solid_tiles = pygame.sprite.Group()
        self.blocking_tiles = pygame.sprite.Group()
        self.overlay_tiles = pygame.sprite.Group()

        self.player = None
        self.player_lives = 3
        self.enemies_to_spawn = 10
        self.enemy_spawns = []
        self._spawn_idx = 0
        self.next_enemy_at = 0

        # Load level
        level = Level("levels/level1.txt")
        data = level.load(self)
        self.player_spawn = data.player_spawn or pygame.Vector2(TILE*12, TILE*24)
        self.enemy_spawns = data.enemy_spawns or [pygame.Vector2(0,0), pygame.Vector2(TILE*24, 0)]
        self.eagle = data.eagle

        self.respawn_player(initial=True)

        # Spawn a few enemies
        for _ in range(min(3, self.enemies_to_spawn)):
            self.spawn_enemy(); self.enemies_to_spawn -= 1

    # --- Tile helpers
    def add_tile(self, t: Tile):
        self.all_sprites.add(t)
        if t.solid:
            self.solid_tiles.add(t)
            self.blocking_tiles.add(t)

    def add_overlay(self, t: Tile):
        self.all_sprites.add(t)
        self.overlay_tiles.add(t)

    # --- Spawning
    def respawn_player(self, initial=False):
        if self.player: self.player.kill()
        if not initial and self.player_lives < 0: return
        p = PlayerTank(self.player_spawn)
        p.invuln_until = pygame.time.get_ticks() + 1500
        self.player = p
        self.players.add(p); self.all_sprites.add(p)

    def spawn_enemy(self):
        if self.enemies_to_spawn <= 0: return
        if not self.enemy_spawns: return
        pos = self.enemy_spawns[self._spawn_idx % len(self.enemy_spawns)]
        self._spawn_idx += 1
        e = EnemyTank(pos)
        e.invuln_until = pygame.time.get_ticks() + 1000
        self.enemies.add(e); self.all_sprites.add(e)

    def restart(self):
        self.setup_world()
        self.state = STATE_PLAYING
        self.state_reason = ""

    # --- UI helpers
    def draw_center_text(self, title, subtitle=""):
        title_surf = self.big.render(title, True, COLOR_UI_ACCENT)
        sub_surf = self.font.render(subtitle, True, COLOR_TEXT)
        rect1 = title_surf.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 10))
        rect2 = sub_surf.get_rect(center=(SCREEN_W//2, SCREEN_H//2 + 22))
        self.screen.blit(title_surf, rect1)
        if subtitle: self.screen.blit(sub_surf, rect2)

    def draw_hud(self):
        # Hearts for lives
        x = 8; y = 4
        for i in range(max(0, self.player_lives)):
            pygame.draw.polygon(self.screen, (255,80,90), [(x+6,y+10),(x+12,y+4),(x+18,y+10),(x+12,y+18)])
            pygame.draw.circle(self.screen, (255,80,90), (x+9, y+8), 4)
            pygame.draw.circle(self.screen, (255,80,90), (x+15, y+8), 4)
            x += 22

        # Enemy count icon
        tank_icon = pygame.Surface((TILE//2, TILE//2)); tank_icon.fill(COLOR_ENEMY)
        self.screen.blit(tank_icon, (SCREEN_W-100, 6))
        remain = self.enemies_to_spawn + len(self.enemies)
        txt = self.font.render(f"x {remain}", True, COLOR_TEXT)
        self.screen.blit(txt, (SCREEN_W-68, 6))

    def draw_menu(self):
        self.screen.fill(COLOR_BG)
        draw_subtle_grid(self.screen)
        self.draw_center_text("BATTLE CITY", "Press ENTER to Start  •  ESC to Quit")

    # --- Main loop
    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                elif event.type == pygame.KEYDOWN:
                    if self.state == STATE_MENU:
                        if event.key == pygame.K_RETURN:
                            self.state = STATE_PLAYING
                        elif event.key == pygame.K_ESCAPE:
                            pygame.quit(); sys.exit(0)
                    elif self.state == STATE_PLAYING:
                        if event.key == pygame.K_ESCAPE:
                            self.state = STATE_MENU
                            self.setup_world()
                        if event.key == pygame.K_SPACE and self.player:
                            self.player.shoot(self)
                    elif self.state in (STATE_GAMEOVER, STATE_VICTORY):
                        if event.key == pygame.K_r:
                            self.restart()
                        if event.key == pygame.K_RETURN:
                            self.state = STATE_MENU
                            self.setup_world()

            # Update
            if self.state == STATE_PLAYING:
                self.players.update(self)
                self.enemies.update(self)
                self.bullets.update(self)

                now = pygame.time.get_ticks()
                if self.enemies_to_spawn > 0 and now > self.next_enemy_at and len(self.enemies) < 4:
                    self.spawn_enemy(); self.enemies_to_spawn -= 1
                    self.next_enemy_at = now + 1600

                if self.enemies_to_spawn == 0 and len(self.enemies) == 0:
                    self.state = STATE_VICTORY
                    self.state_reason = "All enemies destroyed."

            # Draw
            self.screen.fill(COLOR_BG)
            draw_subtle_grid(self.screen)

            if self.state == STATE_MENU:
                self.draw_menu()
            else:
                # base + tiles
                for spr in self.all_sprites:
                    if spr in self.overlay_tiles: continue
                    self.screen.blit(spr.image, spr.rect)

                # tanks
                for spr in self.players: 
                    # spawn shield blink
                    if pygame.time.get_ticks() < spr.invuln_until and (pygame.time.get_ticks()//120)%2==0:
                        pass  # blink off
                    else:
                        self.screen.blit(spr.image, spr.rect)
                for spr in self.enemies:
                    if pygame.time.get_ticks() < spr.invuln_until and (pygame.time.get_ticks()//120)%2==0:
                        pass
                    else:
                        self.screen.blit(spr.image, spr.rect)

                # bullets
                for spr in self.bullets: self.screen.blit(spr.image, spr.rect)

                # overlay
                for spr in self.overlay_tiles: self.screen.blit(spr.image, spr.rect)

                # HUD
                self.draw_hud()

                # overlays for end states
                if self.state == STATE_GAMEOVER:
                    self.draw_center_text("GAME OVER", f"{self.state_reason}  •  Press R to Restart or ENTER for Menu")
                elif self.state == STATE_VICTORY:
                    self.draw_center_text("YOU WIN!", "Press R to Replay or ENTER for Menu")

            pygame.display.flip()

if __name__ == "__main__":
    Game().run()
