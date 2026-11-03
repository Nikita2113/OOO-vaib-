import pygame
import random
import math
import sys

pygame.init()
WIDTH, HEIGHT = 1400, 750
SCREEN_W, SCREEN_H = 1200, 650
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Worms 2D - Classic Style")
clock = pygame.time.Clock()

WATER_LEVEL = HEIGHT - 50
GRAVITY = 0.4
PROJECTILE_GRAVITY = 0.25  # ★ Меньше гравитация для снарядов — летят дальше
WORM_SPEED = 2.5
JUMP_FORCE = -9
CLIMB_STEP = 15
MAX_CLIMB_HEIGHT = 40  # ★ Макс высота которую может перелезть
PARACHUTE_DRIFT = 1.8


class TerrainMap:
    def __init__(self, width, height, color, dark_color=None):
        self.width = max(1, width)
        self.height = max(1, height)
        self.color = color
        self.dark_color = dark_color or tuple(max(0, c - 40) for c in color)
        self.map = [[False] * self.width for _ in range(self.height)]
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.dirty = True
        self.decorations = []

    def set_solid(self, x, y, value=True):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.map[y][x] = value
            self.dirty = True

    def is_solid(self, x, y):
        ix, iy = int(x), int(y)
        if 0 <= ix < self.width and 0 <= iy < self.height:
            return self.map[iy][ix]
        return False

    def carve_circle(self, cx, cy, radius):
        r = int(radius)
        for y in range(max(0, int(cy) - r), min(self.height, int(cy) + r)):
            for x in range(max(0, int(cx) - r), min(self.width, int(cx) + r)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                    if self.map[y][x]:
                        self.map[y][x] = False
                        self.dirty = True

    def carve_rect(self, x1, y1, x2, y2):
        for y in range(max(0, int(y1)), min(self.height, int(y2))):
            for x in range(max(0, int(x1)), min(self.width, int(x2))):
                if self.map[y][x]:
                    self.map[y][x] = False
                    self.dirty = True

    def fill_rect(self, x1, y1, x2, y2):
        for y in range(max(0, int(y1)), min(self.height, int(y2))):
            for x in range(max(0, int(x1)), min(self.width, int(x2))):
                if not self.map[y][x]:
                    self.map[y][x] = True
                    self.dirty = True

    def generate_decorations(self):
        self.decorations = []
        step = max(6, self.width // 100)
        for x in range(0, self.width, random.randint(step, step + 10)):
            for y in range(self.height):
                if self.map[y][x] and (y == 0 or not self.map[y - 1][x]):
                    dt = random.choice(['grass', 'grass', 'grass', 'rock', 'flower'])
                    if dt == 'grass':
                        self.decorations.append(('grass', x, y, random.randint(3, 8)))
                    elif dt == 'rock':
                        self.decorations.append(('rock', x, y, random.randint(2, 4)))
                    elif dt == 'flower':
                        c = random.choice([(255, 100, 100), (255, 255, 100), (255, 150, 255), (100, 200, 255)])
                        self.decorations.append(('flower', x, y, c))
                    break

    def rebuild_surface(self):
        if not self.dirty: return
        self.surface.fill((0, 0, 0, 0))
        dark = self.dark_color
        for y in range(self.height):
            row = self.map[y]
            x = 0
            while x < self.width:
                if row[x]:
                    start = x
                    while x < self.width and row[x]: x += 1
                    pygame.draw.rect(self.surface, self.color, (start, y, x - start, 1))
                    if y == 0 or not self.map[y - 1][start]:
                        pygame.draw.rect(self.surface, dark, (start, y, x - start, 1))
                else:
                    x += 1
        for dec in self.decorations:
            if dec[0] == 'grass':
                _, dx, dy, h = dec
                if dy < self.height and not self.map[dy][dx]:
                    pygame.draw.line(self.surface, (50, 140, 50), (dx, dy), (dx - 2, dy - h), 1)
                    pygame.draw.line(self.surface, (50, 140, 50), (dx, dy), (dx + 2, dy - h + 1), 1)
            elif dec[0] == 'rock':
                _, dx, dy, s = dec
                if dy - s > 0 and not self.map[dy - s][dx]:
                    pygame.draw.circle(self.surface, (130, 120, 110), (dx, dy - s // 2), s)
            elif dec[0] == 'flower':
                _, dx, dy, c = dec
                if dy - 5 > 0 and not self.map[dy - 5][dx]:
                    pygame.draw.line(self.surface, (50, 130, 50), (dx, dy), (dx, dy - 4), 1)
                    pygame.draw.circle(self.surface, c, (dx, dy - 5), 2)
        self.dirty = False

    def get_surface(self):
        self.rebuild_surface()
        return self.surface


class Worm:
    def __init__(self, x, y, team, name, color, direction=1):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = 0.0, 0.0
        self.team = team
        self.name = name
        self.color = color
        self.health = 100
        self.alive = True
        self.direction = direction
        self.angle = 0.0
        self.on_ground = False
        self.walk_frame = 0
        self.walk_timer = 0
        self.parachute = False

    def update_animation(self, moving=False):
        if moving:
            self.walk_timer += 1
            if self.walk_timer >= 8:
                self.walk_timer = 0
                self.walk_frame = (self.walk_frame + 1) % 4
        else:
            self.walk_frame = 0
            self.walk_timer = 0

    def draw(self, surface, is_active, cam_x, cam_y):
        if not self.alive: return
        sx, sy = int(self.x - cam_x), int(self.y - cam_y)
        if sx < -50 or sx > SCREEN_W + 50 or sy < -50 or sy > SCREEN_H + 50: return

        if self.parachute:
            t = pygame.time.get_ticks() / 200
            sw = math.sin(t) * 2
            pygame.draw.arc(surface, (255, 255, 255), (sx - 18 + sw, sy - 38, 36, 24), 0, math.pi, 2)
            pygame.draw.line(surface, (200, 200, 200), (sx - 14 + sw, sy - 18), (sx, sy - 5), 1)
            pygame.draw.line(surface, (200, 200, 200), (sx + 14 + sw, sy - 18), (sx, sy - 5), 1)

        lo = math.sin(self.walk_frame * math.pi / 2) * 3
        if self.on_ground:
            pygame.draw.rect(surface, (60, 60, 60), (sx - 6, sy + 10, 4, 8 + lo))
            pygame.draw.rect(surface, (40, 40, 40), (sx - 7, sy + 17 + lo, 6, 3))
            pygame.draw.rect(surface, (60, 60, 60), (sx + 2, sy + 10, 4, 8 - lo))
            pygame.draw.rect(surface, (40, 40, 40), (sx + 1, sy + 17 - lo, 6, 3))
        else:
            pygame.draw.rect(surface, (60, 60, 60), (sx - 5, sy + 8, 4, 6))
            pygame.draw.rect(surface, (60, 60, 60), (sx + 1, sy + 8, 4, 6))

        pygame.draw.ellipse(surface, self.color, (sx - 8, sy - 5, 16, 20))
        pygame.draw.ellipse(surface, tuple(max(0, c - 30) for c in self.color), (sx - 8, sy - 5, 16, 20), 2)

        if self.direction == 1:
            pygame.draw.line(surface, (255, 213, 176), (sx + 5, sy), (sx + 12, sy - 3), 3)
            pygame.draw.rect(surface, (80, 80, 80), (sx + 10, sy - 5, 8, 3))
        else:
            pygame.draw.line(surface, (255, 213, 176), (sx - 5, sy), (sx - 12, sy - 3), 3)
            pygame.draw.rect(surface, (80, 80, 80), (sx - 18, sy - 5, 8, 3))

        pygame.draw.circle(surface, (255, 213, 176), (sx, sy - 12), 9)
        pygame.draw.arc(surface, self.color, (sx - 9, sy - 21, 18, 12), 0, math.pi, 3)
        ex = sx + self.direction * 3
        pygame.draw.circle(surface, (255, 255, 255), (ex - 2, sy - 14), 3)
        pygame.draw.circle(surface, (255, 255, 255), (ex + 2, sy - 14), 3)
        pygame.draw.circle(surface, (0, 0, 0), (ex - 2 + self.direction, sy - 14), 1)
        pygame.draw.circle(surface, (0, 0, 0), (ex + 2 + self.direction, sy - 14), 1)

        if self.health < 100:
            bw, hw = 26, int(26 * self.health / 100)
            pygame.draw.rect(surface, (0, 0, 0), (sx - 13, sy - 30, bw + 2, 6))
            hc = (0, 200, 0) if self.health > 50 else (255, 165, 0) if self.health > 25 else (255, 0, 0)
            pygame.draw.rect(surface, hc, (sx - 12, sy - 29, hw, 4))

        if is_active:
            b = math.sin(pygame.time.get_ticks() / 200) * 3
            pygame.draw.polygon(surface, (255, 215, 0),
                                [(sx, sy - 38 + b), (sx - 6, sy - 46 + b), (sx + 6, sy - 46 + b)])
            f = pygame.font.Font(None, 16)
            nt = f.render(self.name, True, (255, 255, 255))
            br = nt.get_rect(center=(sx, sy - 55))
            pygame.draw.rect(surface, (0, 0, 0), br.inflate(4, 2))
            surface.blit(nt, br)


class Projectile:
    def __init__(self, x, y, vx, vy, wtype, damage, blast):
        self.x, self.y, self.vx, self.vy = float(x), float(y), float(vx), float(vy)
        self.type = wtype
        self.damage, self.blast_radius = damage, blast
        self.active = True
        self.timer = 180 if wtype == 'grenade' else 300
        self.bounces = 3 if wtype in ('grenade', 'banana') else 0
        self.trail = []
        self.max_trail = 30
        if wtype == 'banana':
            self.timer, self.blast_radius, self.damage = 240, 80, 80
        if wtype == 'mine':
            self.timer, self.bounces, self.vy, self.vx = 9999, 0, 0, 0
            self.arm_timer, self.armed = 90, False
        if wtype == 'air_strike':
            self.timer, self.bounces = 9999, 0

    def add_trail_point(self):
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.max_trail:
            self.trail.pop(0)


# ======== ГЕНЕРАТОРЫ ========

def generate_classic_hills(width, height):
    terrain = TerrainMap(width, height, (85, 130, 65), (65, 100, 45))
    scale = width / 1400
    num_hills = max(3, int(6 * scale + random.randint(0, 3)))
    for _ in range(num_hills):
        hx = random.randint(int(width * 0.05), max(int(width * 0.05) + 1, int(width * 0.95)))
        hw = max(20, int(random.randint(80, 200) * scale))
        hh = max(20, int(random.randint(100, 300) * (height / 750)))
        base_y = height - 50
        for x in range(max(0, hx - hw // 2), min(width, hx + hw // 2)):
            dist = abs(x - hx)
            half_w = max(1, hw / 2)
            hatx = hh * max(0, 1 - (dist / half_w) ** 2)
            for y in range(max(0, int(base_y - hatx)), height):
                terrain.set_solid(x, y, True)
    for _ in range(max(1, int(3 * scale))):
        vx = random.randint(int(width * 0.1), max(int(width * 0.1) + 1, int(width * 0.9)))
        vw = max(10, int(random.randint(40, 80) * scale))
        vd = max(5, int(random.randint(30, 60) * (height / 750)))
        for x in range(max(0, vx - vw // 2), min(width, vx + vw // 2)):
            for y in range(max(0, height - 50 - vd), height - 50):
                terrain.set_solid(x, y, False)
    for _ in range(max(1, int(4 * scale))):
        cx = random.randint(int(width * 0.1), max(int(width * 0.1) + 1, int(width * 0.9)))
        cy = random.randint(int(height * 0.4), max(int(height * 0.4) + 1, int(height * 0.75)))
        cw = max(10, int(random.randint(30, 50) * scale))
        ch = max(8, int(random.randint(25, 40) * (height / 750)))
        terrain.carve_rect(cx, cy, cx + cw, cy + ch)
    if width > 100:
        for _ in range(max(1, int(2 * scale))):
            px = random.randint(int(width * 0.15), max(int(width * 0.15) + 1, int(width * 0.85)))
            py = random.randint(int(height * 0.3), max(int(height * 0.3) + 1, int(height * 0.55)))
            pw = max(15, int(random.randint(60, 100) * scale))
            terrain.fill_rect(px, py, px + pw, py + max(3, int(10 * height / 750)))
    terrain.generate_decorations()
    spawn_points = []
    for i in range(3):
        x = max(10, int(width * 0.1 + i * width * 0.1))
        y = 10
        while y < height - 5 and not terrain.is_solid(x, y): y += 1
        spawn_points.append((x, max(10, y - 20)))
    for i in range(3):
        x = max(10, int(width * 0.9 - i * width * 0.1))
        y = 10
        while y < height - 5 and not terrain.is_solid(x, y): y += 1
        spawn_points.append((x, max(10, y - 20)))
    return terrain, spawn_points


def generate_islands(width, height):
    terrain = TerrainMap(width, height, (80, 140, 70), (60, 110, 50))
    scale = width / 1400
    islands = [(int(width * 0.15), int(width * 0.35)), (int(width * 0.4), int(width * 0.6)),
               (int(width * 0.65), int(width * 0.85))]
    for x1, x2 in islands:
        cx = (x1 + x2) // 2
        max_h = int(200 * height / 750)
        for x in range(max(0, x1), min(width, x2)):
            dist = abs(x - cx)
            max_dist = max(1, (x2 - x1) / 2)
            h = max_h * max(0, 1 - (dist / max_dist) ** 2)
            for y in range(max(0, int(height - 50 - h)), height):
                terrain.set_solid(x, y, True)
        if width > 80:
            cave_x = cx - max(5, int(25 * scale))
            terrain.carve_rect(cave_x, height - 80, cave_x + max(10, int(50 * scale)),
                               height - 80 + max(8, int(35 * height / 750)))
    if width > 100:
        terrain.fill_rect(int(width * 0.35), int(height * 0.6), int(width * 0.4), int(height * 0.6) + 10)
        terrain.fill_rect(int(width * 0.6), int(height * 0.6), int(width * 0.65), int(height * 0.6) + 10)
    terrain.generate_decorations()
    sp = []
    for i in range(3):
        x = max(10, int(width * 0.15 + i * 30));
        y = 10
        while y < height - 5 and not terrain.is_solid(x, y): y += 1
        sp.append((x, max(10, y - 20)))
    for i in range(3):
        x = max(10, int(width * 0.85 - i * 30));
        y = 10
        while y < height - 5 and not terrain.is_solid(x, y): y += 1
        sp.append((x, max(10, y - 20)))
    return terrain, sp


def generate_valley(width, height):
    terrain = TerrainMap(width, height, (110, 100, 70), (85, 75, 50))
    for x in range(max(0, int(width * 0.05)), min(width, int(width * 0.35))):
        dist = abs(x - int(width * 0.2));
        half = max(1, width * 0.15)
        h = int(280 * height / 750) * max(0, 1 - (dist / half) ** 2)
        for y in range(max(0, int(height - 50 - h)), height): terrain.set_solid(x, y, True)
    for x in range(max(0, int(width * 0.65)), min(width, int(width * 0.95))):
        dist = abs(x - int(width * 0.8));
        half = max(1, width * 0.15)
        h = int(280 * height / 750) * max(0, 1 - (dist / half) ** 2)
        for y in range(max(0, int(height - 50 - h)), height): terrain.set_solid(x, y, True)
    for x in range(max(0, int(width * 0.4)), min(width, int(width * 0.6))):
        dist = abs(x - width // 2);
        half = max(1, width * 0.1)
        h = int(80 * height / 750) * max(0, 1 - (dist / half) ** 2)
        for y in range(max(0, int(height - 50 - h)), height): terrain.set_solid(x, y, True)
    if width > 80:
        s = width / 1400
        terrain.carve_rect(int(width * 0.1), int(height * 0.47), int(width * 0.1) + max(10, int(50 * s)),
                           int(height * 0.47) + max(8, int(40 * height / 750)))
        terrain.carve_rect(int(width * 0.85), int(height * 0.47), int(width * 0.85) + max(10, int(50 * s)),
                           int(height * 0.47) + max(8, int(40 * height / 750)))
    terrain.generate_decorations()
    sp = []
    for i in range(3):
        x = max(10, int(width * 0.1 + i * 30));
        y = 10
        while y < height - 5 and not terrain.is_solid(x, y): y += 1
        sp.append((x, max(10, y - 20)))
    for i in range(3):
        x = max(10, int(width * 0.9 - i * 30));
        y = 10
        while y < height - 5 and not terrain.is_solid(x, y): y += 1
        sp.append((x, max(10, y - 20)))
    return terrain, sp


MAPS = [
    {"name": "Classic Hills", "desc": "Rolling hills & caves", "generator": generate_classic_hills,
     "terrain_color": (85, 130, 65), "sky_top": (30, 60, 140), "sky_bottom": (120, 180, 240)},
    {"name": "Islands", "desc": "Three close islands", "generator": generate_islands,
     "terrain_color": (80, 140, 70), "sky_top": (20, 40, 100), "sky_bottom": (80, 160, 230)},
    {"name": "Valley", "desc": "Hills with valley", "generator": generate_valley,
     "terrain_color": (110, 100, 70), "sky_top": (60, 40, 100), "sky_bottom": (180, 140, 200)},
]

# ★ УВЕЛИЧЕННЫЕ СКОРОСТИ — снаряды летят дальше!
WEAPONS = {
    'bazooka': {'name': 'Bazooka', 'damage': 50, 'blast': 40, 'speed': 18, 'ammo': -1, 'type': 'projectile',
                'desc': 'Wind rocket', 'trail_color': (255, 200, 100)},
    'grenade': {'name': 'Grenade', 'damage': 45, 'blast': 50, 'speed': 14, 'ammo': 3, 'type': 'projectile',
                'desc': 'Bounces 3s', 'trail_color': (255, 100, 0)},
    'shotgun': {'name': 'Shotgun', 'damage': 30, 'speed': 30, 'ammo': 4, 'type': 'shotgun', 'desc': '8x30dmg',
                'pellets': 8, 'spread': 0.2, 'knockback': 15, 'range': 300},
    'sniper': {'name': 'Sniper', 'damage': 70, 'blast': 5, 'speed': 50, 'ammo': 2, 'type': 'hitscan',
               'desc': '70dmg instant'},
    'banana': {'name': 'Banana', 'damage': 80, 'blast': 80, 'speed': 12, 'ammo': 1, 'type': 'projectile',
               'desc': 'HUGE boom!', 'trail_color': (255, 255, 0)},
    'mine': {'name': 'Mine', 'damage': 60, 'blast': 45, 'speed': 0, 'ammo': 2, 'type': 'placeable', 'desc': '1.5s arm'},
    'airstrike': {'name': 'AirStrike', 'damage': 40, 'blast': 35, 'speed': 0, 'ammo': 1, 'type': 'airstrike',
                  'desc': '6 sky bombs', 'trail_color': (255, 50, 50)},
    'parachute': {'name': 'Parachute', 'damage': 0, 'blast': 0, 'speed': 0, 'ammo': 1, 'type': 'parachute',
                  'desc': 'Drift in air'},
}

TEAM_NAMES = ['Green', 'Red', 'Blue', 'Orange']
TEAM_COLORS = [(76, 175, 80), (244, 67, 54), (33, 150, 243), (255, 152, 0)]
WORM_NAMES = [['Bob', 'Jim', 'Fred'], ['Hans', 'Fritz', 'Karl'], ['Ivan', 'Boris', 'Dmitri'],
              ['Pierre', 'Jean', 'Louis']]


def damage_worms(worms, particles, dtexts, cx, cy, radius, damage):
    for w in worms:
        if not w.alive: continue
        dist = math.sqrt((w.x - cx) ** 2 + (w.y - cy) ** 2)
        if dist < radius:
            dmg = max(1, int(damage * (1 - dist / radius)))
            w.health -= dmg
            dtexts.append(
                {'x': w.x, 'y': w.y - 30, 'text': f'-{dmg}', 'color': (255, 80, 80), 'life': 60, 'max_life': 60})
            if dist > 0:
                f = (1 - dist / radius) * 8
                w.vx += (w.x - cx) / dist * f;
                w.vy += (w.y - cy) / dist * f - 3
                w.on_ground = False
            if w.health <= 0:
                w.health, w.alive = 0, False
                dtexts.append(
                    {'x': w.x, 'y': w.y - 50, 'text': 'KILLED!', 'color': (255, 215, 0), 'life': 80, 'max_life': 80})


def boom_particles(particles, cx, cy):
    for _ in range(25):
        a = random.random() * math.pi * 2;
        s = random.random() * 4 + 2
        particles.append({'x': cx, 'y': cy, 'vx': math.cos(a) * s, 'vy': math.sin(a) * s, 'life': 30,
                          'color': random.choice([(255, 100, 0), (255, 200, 0), (255, 50, 0), (255, 255, 100)])})


def draw_trail(surface, trail, color, cam_x, cam_y):
    if len(trail) < 2: return
    for i in range(1, len(trail)):
        alpha = i / len(trail)
        c = tuple(int(color[j] * alpha) for j in range(3))
        thickness = max(1, int(3 * alpha))
        pygame.draw.line(surface, c,
                         (int(trail[i - 1][0] - cam_x), int(trail[i - 1][1] - cam_y)),
                         (int(trail[i][0] - cam_x), int(trail[i][1] - cam_y)), thickness)


# ======== ★ НОВАЯ МЕХАНИКА ДВИЖЕНИЯ С КАРАБКАНЬЕМ ========

def move_worm(terrain, worm, direction):
    """
    Пробует двигать червяка. Возвращает True если удалось.
    Механика:
    1. Идём вперёд по ровной поверхности
    2. Подъём до CLIMB_STEP — автоматический
    3. Стена выше CLIMB_STEP — карабкаемся ВВЕРХ (как в оригинале!)
    4. Обрыв — идём в воздух
    """
    new_x = int(worm.x + direction * WORM_SPEED)
    if new_x < 10 or new_x > WIDTH - 10:
        return False

    worm_y = int(worm.y)
    feet_y = worm_y + 18  # ноги

    # Проверяем что впереди на уровне ног есть земля
    front_feet_solid = terrain.is_solid(new_x, feet_y)

    # Проверяем что впереди на уровне головы свободно
    head_blocked = any(terrain.is_solid(new_x, worm_y + dy) for dy in range(-16, -2))

    if not head_blocked:
        # Голова свободна — ищем поверхность под ногами впереди
        # Сначала проверяем ровную поверхность
        if front_feet_solid:
            worm.x = new_x
            worm.y = feet_y - 18
            return True

        # Ищем землю ниже (спуск)
        check_y = feet_y
        while check_y < HEIGHT - 10 and not terrain.is_solid(new_x, check_y):
            check_y += 1

        if check_y < HEIGHT - 10:
            drop = check_y - feet_y
            if drop <= CLIMB_STEP * 2:  # Можно спуститься
                worm.x = new_x
                worm.y = check_y - 18
                return True
            else:
                # Обрыв — идём в воздух
                worm.x = new_x
                worm.on_ground = False
                return True
        else:
            # Нет земли — обрыв
            worm.x = new_x
            worm.on_ground = False
            return True

    else:
        # ★ СТЕНА ВПЕРЕДИ — КАРАБКАЕМСЯ ВВЕРХ!
        # Проверяем что над головой есть место
        above_free = not terrain.is_solid(int(worm.x), worm_y - 18)
        if above_free:
            # Поднимаемся на 2 пикселя (не двигаясь по X)
            worm.y -= 2
            # Проверяем что не уперлись в потолок
            if terrain.is_solid(int(worm.x), int(worm.y) - 16):
                worm.y += 2  # Возвращаем
                return False
            return True
        return False  # Уперлись в потолок


def show_setup_menu():
    selected_map = 0
    selected_teams = 0
    team_counts = [2, 3, 4]
    font_big = pygame.font.Font(None, 64)
    font_med = pygame.font.Font(None, 40)
    font_small = pygame.font.Font(None, 28)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: pygame.quit(); sys.exit()
                if event.key == pygame.K_LEFT: selected_map = (selected_map - 1) % len(MAPS)
                if event.key == pygame.K_RIGHT: selected_map = (selected_map + 1) % len(MAPS)
                if event.key == pygame.K_UP: selected_teams = max(0, selected_teams - 1)
                if event.key == pygame.K_DOWN: selected_teams = min(len(team_counts) - 1, selected_teams + 1)
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return MAPS[selected_map], team_counts[selected_teams]

        screen.fill((15, 15, 30))
        screen.blit(font_big.render("WORMS 2D", True, (255, 215, 0)), (SCREEN_W // 2 - 100, 15))
        screen.blit(font_med.render("STEP 1: Choose Map", True, (100, 200, 255)), (30, 70))
        screen.blit(font_small.render("< > to select", True, (150, 150, 150)), (30, 105))

        card_w, card_h, gap = 280, 150, 15
        total_w = len(MAPS) * card_w + (len(MAPS) - 1) * gap
        start_x = (SCREEN_W - total_w) // 2

        for i, md in enumerate(MAPS):
            cx, cy = start_x + i * (card_w + gap), 130
            is_sel = (i == selected_map)
            pygame.draw.rect(screen, (60, 60, 90) if is_sel else (40, 40, 60), (cx, cy, card_w, card_h))
            pygame.draw.rect(screen, (255, 215, 0) if is_sel else (80, 80, 100), (cx, cy, card_w, card_h),
                             3 if is_sel else 1)

            pw, ph = card_w - 16, card_h - 30
            preview, _ = md["generator"](pw, ph)
            ps = pygame.Surface((pw, ph))
            for py in range(ph):
                r = py / max(1, ph)
                c = (int(md["sky_top"][0] * (1 - r) + md["sky_bottom"][0] * r),
                     int(md["sky_top"][1] * (1 - r) + md["sky_bottom"][1] * r),
                     int(md["sky_top"][2] * (1 - r) + md["sky_bottom"][2] * r))
                pygame.draw.line(ps, c, (0, py), (pw - 1, py))
            for px in range(pw):
                for py in range(ph):
                    if preview.is_solid(px, py):
                        ps.set_at((px, py), md["terrain_color"])
            screen.blit(ps, (cx + 8, cy + 8))

            nt = font_small.render(md["name"], True, (255, 215, 0) if is_sel else (200, 200, 200))
            screen.blit(nt, (cx + card_w // 2 - nt.get_width() // 2, cy + card_h + 5))

            if is_sel:
                ay = cy - 12 + math.sin(pygame.time.get_ticks() / 300) * 4
                pygame.draw.polygon(screen, (255, 215, 0), [(cx + card_w // 2, ay + 10), (cx + card_w // 2 - 6, ay),
                                                            (cx + card_w // 2 + 6, ay)])

        screen.blit(font_med.render("STEP 2: Choose Teams", True, (100, 200, 255)), (30, 350))
        screen.blit(font_small.render("^ v to select", True, (150, 150, 150)), (30, 385))

        for i, count in enumerate(team_counts):
            bx, by = SCREEN_W // 2 - 195 + i * 140, 410
            is_sel = (i == selected_teams)
            pygame.draw.rect(screen, (60, 60, 100) if is_sel else (40, 40, 60), (bx, by, 120, 80))
            pygame.draw.rect(screen, (255, 215, 0) if is_sel else (80, 80, 100), (bx, by, 120, 80), 3 if is_sel else 1)
            for t in range(count):
                pygame.draw.circle(screen, TEAM_COLORS[t], (bx + 15 + t * 28, by + 30), 10)
                pygame.draw.circle(screen, (255, 255, 255), (bx + 15 + t * 28, by + 30), 10, 2)
            ct = font_small.render(f"{count} Teams", True, (255, 215, 0) if is_sel else (200, 200, 200))
            screen.blit(ct, (bx + 60 - ct.get_width() // 2, by + 55))

        h = font_small.render("ENTER to Start Game", True, (255, 255, 100))
        screen.blit(h, (SCREEN_W // 2 - h.get_width() // 2, SCREEN_H - 40))
        pygame.display.flip()
        clock.tick(60)


def draw_clouds(surface, cam_x, cam_y, t):
    for bx, by, sz in [(100, 50, 80), (400, 80, 60), (700, 40, 90), (1000, 70, 70), (1300, 50, 85)]:
        cx = ((bx + t * 8) % (WIDTH + 200)) - 100 - int(cam_x)
        cy = by - int(cam_y)
        if -150 < cx < SCREEN_W + 50:
            pygame.draw.ellipse(surface, (255, 255, 255), (cx, cy, sz, sz // 2))
            pygame.draw.ellipse(surface, (255, 255, 255), (cx + sz // 3, cy - sz // 4, sz // 2, sz // 2))


def show_victory_screen(winner_team, teams):
    fb = pygame.font.Font(None, 80)
    fs = pygame.font.Font(None, 32)
    confetti = [{'x': random.randint(0, SCREEN_W), 'y': random.randint(-SCREEN_H, 0),
                 'vx': random.uniform(-2, 2), 'vy': random.uniform(2, 5),
                 'color': random.choice(
                     [(255, 215, 0), (255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 100, 255)]),
                 'size': random.randint(3, 8)} for _ in range(100)]

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_RETURN, pygame.K_SPACE): return True
                if ev.key == pygame.K_ESCAPE: pygame.quit(); sys.exit()

        screen.fill((20, 20, 40))
        for c in confetti:
            c['x'] += c['vx'];
            c['y'] += c['vy']
            if c['y'] > SCREEN_H: c['y'] = -10; c['x'] = random.randint(0, SCREEN_W)
            pygame.draw.rect(screen, c['color'], (c['x'], c['y'], c['size'], c['size']))

        if winner_team is not None and winner_team >= 0:
            t = fb.render(f"{teams[winner_team]['name']} WINS!", True, teams[winner_team]['color'])
            s = fb.render(f"{teams[winner_team]['name']} WINS!", True, (0, 0, 0))
            screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2 + 3, SCREEN_H // 3 - s.get_height() // 2 + 3))
            screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, SCREEN_H // 3 - t.get_height() // 2))
        else:
            t = fb.render("DRAW!", True, (200, 200, 200))
            screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, SCREEN_H // 3))

        screen.blit(fs.render("Press ENTER to play again", True, (255, 255, 100)),
                    (SCREEN_W // 2 - 150, SCREEN_H * 2 // 3))
        screen.blit(fs.render("Press ESC to quit", True, (150, 150, 150)),
                    (SCREEN_W // 2 - 100, SCREEN_H * 2 // 3 + 40))
        pygame.display.flip()
        clock.tick(60)


def reset_game():
    """Полный рестарт — возвращает все начальные значения"""
    sm, nt = show_setup_menu()
    terrain, sp = sm["generator"](WIDTH, HEIGHT)
    st, sb = sm["sky_top"], sm["sky_bottom"]

    sky = pygame.Surface((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        r = y / HEIGHT
        c = (int(st[0] * (1 - r) + sb[0] * r), int(st[1] * (1 - r) + sb[1] * r), int(st[2] * (1 - r) + sb[2] * r))
        pygame.draw.line(sky, c, (0, y), (WIDTH, y))

    teams = [{"name": TEAM_NAMES[t], "color": TEAM_COLORS[t]} for t in range(nt)]
    worms = []
    for t in range(nt):
        d = 1 if t == 0 else -1
        for i in range(3):
            if nt <= 2 and len(sp) >= 6:
                x, y = sp[t * 3 + i]
            else:
                idx = t * 3 + i
                if idx < len(sp):
                    x, y = sp[idx]
                else:
                    x = random.randint(100, WIDTH - 100);
                    sy = 10
                    while sy < HEIGHT - 5 and not terrain.is_solid(x, sy): sy += 1
                    y = max(20, sy - 20)
            worms.append(Worm(x, y, t, WORM_NAMES[t][i], TEAM_COLORS[t], d))

    loadout = {w: {wn: wd['ammo'] for wn, wd in WEAPONS.items()} for w in worms}
    return terrain, sp, sky, st, sb, teams, worms, nt, loadout


def main():
    terrain, spawn_points, sky, sky_top, sky_bottom, teams, worms, num_teams, loadout = reset_game()

    ct, cwi = 0, 0
    phase = 'aiming'
    power = 0.0
    wind = random.uniform(-0.08, 0.08)
    projs, parts, dtexts = [], [], []
    sel_wp = 'bazooka'
    timer = 45 * 60
    cam_x, cam_y = 0.0, 0.0

    def alive_of(team):
        return [w for w in worms if w.team == team and w.alive]

    def active():
        a = alive_of(ct)
        return a[cwi % len(a)] if a else None

    def next_turn():
        nonlocal ct, cwi, phase, timer, wind
        for _ in range(num_teams):
            ct = (ct + 1) % num_teams
            if alive_of(ct): break
        if alive_of(ct): cwi = 0
        phase = 'aiming';
        timer = 45 * 60
        wind = random.uniform(-0.08, 0.08)

    def explode(cx, cy, br, dmg):
        terrain.carve_circle(cx, cy, br)
        damage_worms(worms, parts, dtexts, cx, cy, br, dmg)
        boom_particles(parts, cx, cy)

    def fire_shotgun(worm):
        wp = WEAPONS['shotgun']
        for _ in range(wp['pellets']):
            a = worm.angle + random.uniform(-wp['spread'], wp['spread'])
            dx, dy = math.cos(a) * worm.direction, math.sin(a)
            px, py = worm.x + worm.direction * 15, worm.y - 5
            trail = [(px, py)]
            hit = False
            for _ in range(wp['range']):
                px += dx * 2;
                py += dy * 2;
                trail.append((px, py))
                for w in worms:
                    if not w.alive or w == worm: continue
                    if math.sqrt((w.x - px) ** 2 + (w.y - py) ** 2) < 20:
                        w.health -= wp['damage']
                        dtexts.append(
                            {'x': w.x, 'y': w.y - 30, 'text': f'-{wp["damage"]}', 'color': (255, 200, 0), 'life': 60,
                             'max_life': 60})
                        w.vx += dx * wp['knockback'] * worm.direction;
                        w.vy += -wp['knockback'] * 0.5;
                        w.on_ground = False
                        if w.health <= 0:
                            w.health, w.alive = 0, False
                            dtexts.append(
                                {'x': w.x, 'y': w.y - 50, 'text': 'KILLED!', 'color': (255, 215, 0), 'life': 80,
                                 'max_life': 80})
                        hit = True
                        for _p in range(8): parts.append(
                            {'x': px, 'y': py, 'vx': random.uniform(-3, 3), 'vy': random.uniform(-4, 0), 'life': 20,
                             'color': (255, 100, 0)})
                        break
                if hit: break
                if terrain.is_solid(int(px), int(py)):
                    for _p in range(5): parts.append(
                        {'x': px, 'y': py, 'vx': random.uniform(-2, 2), 'vy': random.uniform(-3, 0), 'life': 15,
                         'color': (255, 200, 50)})
                    break
                if px < 0 or px > WIDTH or py < 0 or py > HEIGHT: break
            for i in range(1, len(trail)):
                al = i / len(trail);
                c = int(255 * al)
                pygame.draw.line(screen, (c, c, int(c * 0.7)),
                                 (int(trail[i - 1][0] - cam_x), int(trail[i - 1][1] - cam_y)),
                                 (int(trail[i][0] - cam_x), int(trail[i][1] - cam_y)), 1)

    def fire_sniper(worm):
        wp = WEAPONS['sniper']
        dx, dy = math.cos(worm.angle) * worm.direction, math.sin(worm.angle)
        px, py = worm.x + worm.direction * 15, worm.y - 5
        tracer = [(px, py)]
        for _ in range(300):
            px += dx * 10;
            py += dy * 10;
            tracer.append((px, py))
            if terrain.is_solid(int(px), int(py)):
                explode(px, py, wp['blast'], wp['damage']);
                break
            for w in worms:
                if not w.alive or w == worm: continue
                if math.sqrt((w.x - px) ** 2 + (w.y - py) ** 2) < 15:
                    w.health -= wp['damage']
                    dtexts.append(
                        {'x': w.x, 'y': w.y - 30, 'text': f'-{wp["damage"]}', 'color': (255, 50, 50), 'life': 60,
                         'max_life': 60})
                    w.vx += dx * 5 * worm.direction;
                    w.vy -= 3;
                    w.on_ground = False
                    if w.health <= 0:
                        w.health, w.alive = 0, False
                        dtexts.append({'x': w.x, 'y': w.y - 50, 'text': 'HEADSHOT!', 'color': (255, 0, 0), 'life': 90,
                                       'max_life': 90})
                    break
            else:
                if px < 0 or px > WIDTH or py < 0 or py > HEIGHT: break
                continue
            break
        for i in range(1, len(tracer)):
            al = i / len(tracer);
            c = int(255 * al)
            pygame.draw.line(screen, (c, c, int(c * 0.5)),
                             (int(tracer[i - 1][0] - cam_x), int(tracer[i - 1][1] - cam_y)),
                             (int(tracer[i][0] - cam_x), int(tracer[i][1] - cam_y)), 2)

    running = True
    while running:
        clock.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: running = False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE: running = False
                if phase in ('aiming', 'power'):
                    worm = active()
                    if worm:
                        if ev.key == pygame.K_SPACE and phase == 'aiming':
                            wt = WEAPONS[sel_wp]['type']
                            if wt in ('hitscan', 'placeable', 'airstrike', 'parachute', 'shotgun'):
                                if loadout[worm].get(sel_wp, 0) != 0:
                                    if sel_wp == 'shotgun':
                                        fire_shotgun(worm)
                                    elif sel_wp == 'sniper':
                                        fire_sniper(worm)
                                    elif sel_wp == 'mine':
                                        projs.append(
                                            Projectile(worm.x, worm.y + 15, 0, 0, 'mine', WEAPONS['mine']['damage'],
                                                       WEAPONS['mine']['blast']))
                                    elif sel_wp == 'airstrike':
                                        wp = WEAPONS['airstrike']
                                        tx = worm.x + math.cos(worm.angle) * 200 * worm.direction
                                        for i in range(6):
                                            bx = tx + random.uniform(-80, 80)
                                            projs.append(Projectile(bx, -20 - i * 30, random.uniform(-0.5, 0.5),
                                                                    3 + random.random() * 2, 'air_strike', wp['damage'],
                                                                    wp['blast']))
                                    elif sel_wp == 'parachute':
                                        worm.parachute = True;
                                        worm.on_ground = False
                                        dtexts.append({'x': worm.x, 'y': worm.y - 40, 'text': 'PARACHUTE!',
                                                       'color': (255, 255, 255), 'life': 60, 'max_life': 60})
                                    if loadout[worm][sel_wp] > 0: loadout[worm][sel_wp] -= 1
                                    phase = 'waiting'
                            else:
                                phase = 'power';
                                power = 0.0
                        if ev.key == pygame.K_j and worm.on_ground:
                            worm.vy = JUMP_FORCE;
                            worm.vx = worm.direction * 3;
                            worm.on_ground = False
                        if ev.key == pygame.K_TAB:
                            a = alive_of(ct)
                            if len(a) > 1: cwi = (cwi + 1) % len(a)
                        wk = list(WEAPONS.keys())
                        for ki, kk in enumerate(
                                [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7,
                                 pygame.K_8]):
                            if ev.key == kk and ki < len(wk): sel_wp = wk[ki]
            if ev.type == pygame.KEYUP:
                if ev.key == pygame.K_SPACE and phase == 'power':
                    worm = active()
                    if worm:
                        wp = WEAPONS[sel_wp]
                        sp = wp['speed'] * (0.3 + power / 100 * 0.7)
                        vx = math.cos(worm.angle) * sp * worm.direction
                        vy = math.sin(worm.angle) * sp
                        projs.append(Projectile(worm.x + worm.direction * 15, worm.y - 5, vx, vy, sel_wp, wp['damage'],
                                                wp['blast']))
                        if loadout[worm][sel_wp] > 0: loadout[worm][sel_wp] -= 1
                        phase = 'waiting';
                        power = 0.0

        if phase == 'power': power = min(100, power + 1.5)
        if phase in ('aiming', 'power'):
            timer -= 1
            if timer <= 0: next_turn()

        keys = pygame.key.get_pressed()
        worm = active()

        if phase in ('aiming', 'power') and worm:
            if keys[pygame.K_UP]:
                worm.angle -= 0.03
                if worm.direction == 1:
                    worm.angle = max(-math.pi * 0.8, worm.angle)
                else:
                    worm.angle = min(math.pi * 0.8, worm.angle)
            if keys[pygame.K_DOWN]:
                worm.angle += 0.03
                if worm.direction == 1:
                    worm.angle = min(0.2, worm.angle)
                else:
                    worm.angle = max(math.pi - 0.2, worm.angle)

        moving = False
        for worm in worms:
            if not worm.alive: continue
            if worm.parachute and not worm.on_ground:
                worm.vy = min(worm.vy, 1.5)
                if keys[pygame.K_LEFT]:
                    worm.vx -= 0.3;
                    worm.vx = max(worm.vx, -PARACHUTE_DRIFT);
                    worm.direction = -1
                elif keys[pygame.K_RIGHT]:
                    worm.vx += 0.3;
                    worm.vx = min(worm.vx, PARACHUTE_DRIFT);
                    worm.direction = 1
                else:
                    worm.vx *= 0.95

            if not worm.on_ground:
                worm.vy += GRAVITY
                worm.x += worm.vx;
                worm.y += worm.vy;
                worm.vx *= 0.98
                fy = int(worm.y + 18);
                cx = int(worm.x)
                if terrain.is_solid(cx, fy):
                    if abs(worm.vy) > 6:
                        fd = int((abs(worm.vy) - 6) * 5);
                        worm.health -= fd
                        if fd > 5: dtexts.append(
                            {'x': worm.x, 'y': worm.y - 30, 'text': f'-{fd}', 'color': (200, 200, 200), 'life': 40,
                             'max_life': 40})
                    while fy > 0 and terrain.is_solid(cx, fy): fy -= 1
                    worm.y = fy - 18;
                    worm.vy = worm.vx = 0;
                    worm.on_ground = True;
                    worm.parachute = False
                if worm.health <= 0:
                    worm.health, worm.alive = 0, False
                    if worm == active(): next_turn()
                if worm.y > HEIGHT - 10:
                    was_active = (worm == active())
                    worm.alive, worm.health = False, 0
                    dtexts.append(
                        {'x': worm.x, 'y': HEIGHT - 50, 'text': 'SPLASH!', 'color': (100, 200, 255), 'life': 60,
                         'max_life': 60})
                    if was_active: next_turn()
            else:
                if not terrain.is_solid(int(worm.x), int(worm.y) + 19):
                    worm.on_ground = False
            worm.x = max(10, min(WIDTH - 10, worm.x))
            for p in projs:
                if p.type == 'mine' and p.active and p.armed and worm.alive:
                    if math.sqrt((worm.x - p.x) ** 2 + (worm.y - p.y) ** 2) < 20 and worm.on_ground:
                        explode(p.x, p.y, p.blast_radius, p.damage);
                        p.active = False

        # ★ ДВИЖЕНИЕ С КАРАБКАНЬЕМ ★
        if phase in ('aiming', 'power'):
            worm = active()
            if worm and worm.on_ground:
                for dk, md in [(pygame.K_LEFT, -1), (pygame.K_RIGHT, 1)]:
                    if keys[dk]:
                        if move_worm(terrain, worm, md):
                            worm.direction = md
                            moving = True
                            # Проверяем что всё ещё на земле
                            if not terrain.is_solid(int(worm.x), int(worm.y) + 19):
                                worm.on_ground = False

        if moving and worm:
            worm.update_animation(True)
        else:
            for w in worms: w.update_animation(False)

        # Снаряды — ★ с PROJECTILE_GRAVITY вместо GRAVITY ★
        for p in projs:
            if not p.active: continue
            if p.type == 'mine':
                if not p.armed:
                    p.arm_timer -= 1
                    if p.arm_timer <= 0: p.armed = True
                if not terrain.is_solid(int(p.x), int(p.y) + 5):
                    p.y += 2
                else:
                    while p.y > 0 and terrain.is_solid(int(p.x), int(p.y)): p.y -= 1
                p.timer -= 1
                if p.timer <= 0: explode(p.x, p.y, p.blast_radius, p.damage); p.active = False
                continue
            if p.type == 'air_strike':
                p.vy += PROJECTILE_GRAVITY * 0.3;
                p.x += p.vx;
                p.y += p.vy;
                p.add_trail_point()
                if terrain.is_solid(int(p.x), int(p.y)): explode(p.x, p.y, p.blast_radius, p.damage); p.active = False
                continue
            p.vy += PROJECTILE_GRAVITY;
            p.vx += wind;
            p.x += p.vx;
            p.y += p.vy;
            p.add_trail_point()
            if terrain.is_solid(int(p.x), int(p.y)):
                if p.bounces > 0:
                    p.vy *= -0.5;
                    p.vx *= 0.7;
                    p.bounces -= 1
                    while terrain.is_solid(int(p.x), int(p.y)): p.y -= 1
                else:
                    explode(p.x, p.y, p.blast_radius, p.damage);
                    p.active = False
            p.timer -= 1
            if p.timer <= 0 and p.active: explode(p.x, p.y, p.blast_radius, p.damage); p.active = False
            if p.x < -50 or p.x > WIDTH + 50 or p.y > HEIGHT + 50: p.active = False

        projs = [p for p in projs if p.active]
        for p in parts: p['x'] += p['vx']; p['y'] += p['vy']; p['vy'] += 0.1; p['life'] -= 1
        parts = [p for p in parts if p['life'] > 0]
        for d in dtexts: d['y'] -= 0.5; d['life'] -= 1
        dtexts = [d for d in dtexts if d['life'] > 0]

        if phase == 'waiting' and not projs:
            at = set(w.team for w in worms if w.alive)
            if len(at) <= 1:
                winner = list(at)[0] if at else None
                show_victory_screen(winner, teams)
                terrain, spawn_points, sky, sky_top, sky_bottom, teams, worms, num_teams, loadout = reset_game()
                ct, cwi, phase = 0, 0, 'aiming'
                projs, parts, dtexts = [], [], []
                timer = 45 * 60;
                wind = random.uniform(-0.08, 0.08)
            else:
                next_turn()

        aw = active()
        if aw:
            cam_x += (aw.x - SCREEN_W // 2 - cam_x) * 0.08
            cam_y += (aw.y - SCREEN_H // 2 - cam_y) * 0.08
            cam_x = max(0, min(WIDTH - SCREEN_W, cam_x))
            cam_y = max(0, min(HEIGHT - SCREEN_H, cam_y))

        # РЕНДЕР
        screen.blit(sky, (-int(cam_x), -int(cam_y)))
        draw_clouds(screen, cam_x, cam_y, pygame.time.get_ticks() / 1000)
        sun_x, sun_y = 100 - int(cam_x), 60 - int(cam_y)
        if -50 < sun_x < SCREEN_W + 50:
            pygame.draw.circle(screen, (255, 240, 150), (sun_x, sun_y), 30)

        wsy = WATER_LEVEL - int(cam_y)
        if wsy < SCREEN_H:
            t = pygame.time.get_ticks() / 1000
            for x in range(0, SCREEN_W, 6):
                wo = math.sin((x + cam_x) * 0.03 + t * 2) * 3
                wy = wsy + wo;
                d = min(80, SCREEN_H - wy)
                if d > 0:
                    pygame.draw.rect(screen, (0, min(255, 80 + int(d * 2)), 200), (x, wy, 6, d))
                    if int(x + cam_x) % 40 < 3: pygame.draw.rect(screen, (150, 200, 255), (x, wy, 3, 1))

        screen.blit(terrain.get_surface(), (-int(cam_x), -int(cam_y)))

        for p in projs:
            if p.type not in ('mine',):
                tc = WEAPONS.get(p.type, {}).get('trail_color', (255, 200, 100))
                draw_trail(screen, p.trail, tc, cam_x, cam_y)

        for p in projs:
            sx, sy = int(p.x - cam_x), int(p.y - cam_y)
            if sx < -20 or sx > SCREEN_W + 20 or sy < -20 or sy > SCREEN_H + 20: continue
            if p.type == 'mine' and p.active:
                pygame.draw.circle(screen, (100, 100, 100), (sx, sy), 6)
                pygame.draw.circle(screen, (255, 0, 0), (sx, sy), 6, 1)
                if p.armed:
                    if pygame.time.get_ticks() % 500 < 250: pygame.draw.circle(screen, (255, 0, 0), (sx, sy), 8)
                else:
                    pr = 1 - p.arm_timer / 90
                    pygame.draw.arc(screen, (0, 255, 0), (sx - 8, sy - 8, 16, 16), -math.pi / 2,
                                    -math.pi / 2 + pr * math.pi * 2, 2)
            elif p.type == 'air_strike':
                pygame.draw.rect(screen, (50, 50, 50), (sx - 3, sy - 6, 6, 12))
            elif p.type == 'banana':
                pygame.draw.circle(screen, (255, 255, 0), (sx, sy), 7)
            elif p.type == 'grenade':
                pygame.draw.circle(screen, (50, 50, 50), (sx, sy), 5)
                if p.timer < 60 and pygame.time.get_ticks() % 200 < 100: pygame.draw.circle(screen, (255, 0, 0),
                                                                                            (sx, sy), 6)
            else:
                pygame.draw.circle(screen, (100, 100, 100), (sx, sy), 4)

        for p in parts:
            sx, sy = int(p['x'] - cam_x), int(p['y'] - cam_y)
            if -10 < sx < SCREEN_W + 10 and -10 < sy < SCREEN_H + 10:
                pygame.draw.circle(screen, p['color'], (sx, sy), max(1, int(3 * p['life'] / 30)))

        for w in worms: w.draw(screen, w == aw, cam_x, cam_y)

        if aw and phase in ('aiming', 'power'):
            wp = WEAPONS[sel_wp]
            sx = int(aw.x + aw.direction * 15 - cam_x);
            sy = int(aw.y - 5 - cam_y)
            if wp['type'] == 'projectile':
                l = 30 + power * 0.3
                ex = sx + int(math.cos(aw.angle) * l * aw.direction);
                ey = sy + int(math.sin(aw.angle) * l)
                pygame.draw.line(screen, (255, 255, 255), (sx, sy), (ex, ey), 2)
            elif wp['type'] in ('hitscan', 'shotgun'):
                l = 200
                ex = sx + int(math.cos(aw.angle) * l * aw.direction);
                ey = sy + int(math.sin(aw.angle) * l)
                pygame.draw.line(screen, (255, 50, 50), (sx, sy), (ex, ey), 1)

        font = pygame.font.Font(None, 22);
        fs = pygame.font.Font(None, 16)
        pygame.draw.rect(screen, (0, 0, 0), (0, 0, SCREEN_W, 45))
        pygame.draw.rect(screen, teams[ct]['color'], (10, 8, 28, 28))
        pygame.draw.rect(screen, (255, 255, 255), (10, 8, 28, 28), 2)
        screen.blit(font.render(teams[ct]['name'], True, (255, 255, 255)), (45, 10))
        tc = (255, 100, 100) if timer // 60 < 10 else (255, 255, 255)
        screen.blit(font.render(f"Time: {timer // 60}s", True, tc), (SCREEN_W // 2 - 40, 5))
        wd = '>>>' if wind > 0 else '<<<'
        screen.blit(font.render(f"Wind: {wd}{abs(wind) * 100:.1f}", True, (200, 200, 200)), (SCREEN_W // 2 - 40, 25))
        for t in range(num_teams):
            th = sum(w.health for w in worms if w.team == t and w.alive)
            ac = sum(1 for w in worms if w.team == t and w.alive)
            tx = SCREEN_W - 140;
            ty = 8 + t * 14
            pygame.draw.rect(screen, TEAM_COLORS[t], (tx, ty, 8, 8))
            screen.blit(fs.render(f"{th}hp ({ac})", True, (200, 200, 200)), (tx + 12, ty - 2))

        py_h = SCREEN_H - 50
        pygame.draw.rect(screen, (0, 0, 0), (0, py_h, SCREEN_W, 50))
        wl = list(WEAPONS.keys());
        ws = 100;
        wx0 = SCREEN_W // 2 - len(wl) * ws // 2
        worm = active()
        for i, wn in enumerate(wl):
            wd = WEAPONS[wn];
            wx = wx0 + i * ws;
            wy = py_h + 4
            sel = (wn == sel_wp);
            am = loadout[worm].get(wn, 0) if worm else 0
            pygame.draw.rect(screen, (80, 80, 120) if sel else (60, 60, 80), (wx, wy, 90, 40))
            if sel: pygame.draw.rect(screen, (255, 215, 0), (wx, wy, 90, 40), 2)
            nc = (255, 255, 255) if am != 0 else (100, 100, 100)
            screen.blit(fs.render(f"{i + 1}:{wd['name'][:8]}", True, nc), (wx + 4, wy + 2))
            at = "inf" if am == -1 else f"x{am}" if am > 0 else "empty"
            ac = (100, 255, 100) if am == -1 else (255, 200, 0) if am > 0 else (255, 80, 80)
            screen.blit(fs.render(at, True, ac), (wx + 4, wy + 18))
            if sel: screen.blit(fs.render(wd['desc'], True, (200, 200, 200)), (wx, wy - 14))
        screen.blit(fs.render("[TAB]Switch [J]Jump [1-8]Weapon [SPACE]Fire [arrows]Aim/Climb", True, (130, 130, 130)),
                    (10, py_h + 36))

        if phase == 'power':
            pygame.draw.rect(screen, (50, 50, 50), (SCREEN_W // 2 - 60, 50, 120, 12))
            bw = int(power / 100 * 118)
            c = (0, 255, 0) if power < 33 else (255, 255, 0) if power < 66 else (255, 100, 0)
            pygame.draw.rect(screen, c, (SCREEN_W // 2 - 59, 51, bw, 10))

        for d in dtexts:
            sx, sy = int(d['x'] - cam_x), int(d['y'] - cam_y)
            tf = pygame.font.Font(None, 20)
            txt = tf.render(d['text'], True, d['color'])
            screen.blit(txt, (sx - txt.get_width() // 2, sy))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()