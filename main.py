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


# ======== ★ ГРАФИЧЕСКИЕ УТИЛИТЫ (аддитивное свечение, шум, градиенты) ========

def _additive_layer(size):
    return pygame.Surface(size, pygame.SRCALPHA)


def glow_dot(layer, x, y, radius, color, core_alpha=180):
    """Мягкое световое пятно (рисуются в аддитивный слой)."""
    r = max(2, int(radius))
    s = _additive_layer((r * 2, r * 2))
    cx = cy = r
    for rr in range(r, 0, -max(1, r // 8)):
        a = int(core_alpha * (rr / r) ** 2)
        pygame.draw.circle(s, (*color, min(255, a)), (cx, cy), rr)
    layer.blit(s, (int(x) - r, int(y) - r), special_flags=pygame.BLEND_PREMULTIPLIED)


def draw_glow_circle(surface, pos, radius, color, core_alpha=200):
    """Светящийся круг поверх сцены."""
    layer = _additive_layer(surface.get_size())
    glow_dot(layer, pos[0], pos[1], radius, color, core_alpha)
    surface.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def value_noise_2d(w, h, seed, scale):
    """Простый целочисленный шум значений с билинейной интерполяцией."""
    rng = random.Random(seed)
    gw, gh = max(2, w // scale + 2), max(2, h // scale + 2)
    grid = [[rng.random() for _ in range(gw)] for _ in range(gh)]

    def smooth(t):
        return t * t * (3 - 2 * t)

    out = [[0.0] * w for _ in range(h)]
    for y in range(h):
        gy, fy = y // scale, smooth((y % scale) / scale)
        for x in range(w):
            gx, fx = x // scale, smooth((x % scale) / scale)
            v00 = grid[gy][gx]; v10 = grid[gy][min(gx + 1, gw - 1)]
            v01 = grid[min(gy + 1, gh - 1)][gx]; v11 = grid[min(gy + 1, gh - 1)][min(gx + 1, gw - 1)]
            out[y][x] = (v00 * (1 - fx) + v10 * fx) * (1 - fy) + (v01 * (1 - fx) + v11 * fx) * fy
    return out


class TerrainMap:
    def __init__(self, width, height, color, dark_color=None, dirt_color=None):
        self.width = max(1, width)
        self.height = max(1, height)
        self.color = color
        self.dirt_color = dirt_color or tuple(max(0, c - 45) for c in (color[0] + 40, color[1] + 5, color[2] - 15))
        self.dark_color = dark_color or tuple(max(0, c - 40) for c in color)
        self.map = [[False] * self.width for _ in range(self.height)]
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.dirty = True
        self.decorations = []
        self.seed = random.randint(0, 10 ** 9)

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
        """★ Полная перерисовка с травою, землёй с шумом, скалами, тенями и подсветкой."""
        if not self.dirty: return
        w, h = self.width, self.height
        self.surface.fill((0, 0, 0, 0))
        try:
            import numpy as np
            arr = pygame.surfarray.pixels3d(self.surface)  # (w, h, 3)
            alpha = pygame.surfarray.pixels_alpha(self.surface)  # (w, h)
            solid = np.array(self.map, dtype=bool).T       # (w, h)
            n1 = np.array(value_noise_2d(w, h, self.seed, 7)).T
            n2 = np.array(value_noise_2d(w, h, self.seed + 999, 23)).T
            # корректная глубина сверху вниз (непрерывный вертикальный прогон):
            colrun = np.zeros((w, h), dtype=int)
            run = np.zeros(w, dtype=int)
            for y in range(h):
                run = np.where(solid[:, y], run + 1, 0)
                colrun[:, y] = run
            dp = colrun
            grass_h = max(4, min(8, int(6 * h / 750)))
            shade = 0.82 + (n1 * 0.6 + n2 * 0.4) * 0.36
            deep_fade = np.clip(1.0 - np.maximum(0, dp - grass_h * 3) * 0.004, 0.55, 1.0)
            rockness = np.clip((dp - grass_h * 2) / max(1.0, h * 0.35), 0, 1)
            tip = np.where(dp <= 2, 1.0, 0.94)
            is_grass = dp <= grass_h
            br_, bg_, bb_ = self.dirt_color
            gr_, gg_, gb_ = self.color
            r = np.where(is_grass, gr_ * tip, br_ * (1 - rockness) + 105 * rockness)
            g = np.where(is_grass, gg_ * tip, bg_ * (1 - rockness) + 98 * rockness)
            b = np.where(is_grass, gb_ * tip, bb_ * (1 - rockness) + 92 * rockness)
            r, g, b = r * shade * deep_fade, g * shade * deep_fade, b * shade * deep_fade
            veins = (~is_grass) & (n2 > 0.78) & (rockness > 0.3)
            r += veins * 28; g += veins * 26; b += veins * 24
            left_edge = solid & ~np.roll(solid, 1, axis=0)
            right_edge = solid & ~np.roll(solid, -1, axis=0)
            left_edge[:, 0] = False; right_edge[:, w - 1] = False
            r += left_edge * 18; g += left_edge * 16; b += left_edge * 12
            r *= 1 - right_edge * 0.2; g *= 1 - right_edge * 0.2; b *= 1 - right_edge * 0.2
            below_solid = np.zeros_like(solid)
            below_solid[:, :-1] = solid[:, 1:]
            bottom_edge = solid & ~below_solid & (dp > grass_h)
            r *= 1 - bottom_edge * 0.4; g *= 1 - bottom_edge * 0.4; b *= 1 - bottom_edge * 0.4
            # тёмная кромка под слоем травы
            under_grass = (dp == grass_h) & ~np.roll(is_grass, -1, axis=1) & is_grass
            r = np.where(under_grass, r * 0.75, r)
            g = np.where(under_grass, g * 0.75, g)
            b = np.where(under_grass, b * 0.75, b)
            arr[..., 0] = np.where(solid, np.clip(r, 0, 255), 0).astype(np.uint8)
            arr[..., 1] = np.where(solid, np.clip(g, 0, 255), 0).astype(np.uint8)
            arr[..., 2] = np.where(solid, np.clip(b, 0, 255), 0).astype(np.uint8)
            alpha[...] = np.where(solid, 255, 0).astype(np.uint8)
            del arr, alpha
        except Exception:
            self._rebuild_surface_slow()

    def _rebuild_surface_slow(self):
        """★ Резервный попиксельный рендер террейна (без numpy)."""
        w, h = self.width, self.height
        grass_h = max(4, min(8, int(6 * h / 750)))
        noise_scale1, noise_scale2 = 7.0, 23.0
        rnd = random.Random(self.seed)
        # шум можно взять из value_noise_2d, но он тяжёлый — используем дешёвый хэш-шум
        def cheap_noise(x, y, seed_off):
            v = ((x * 73856093) ^ (y * 19349663) ^ ((self.seed + seed_off) * 83492791)) & 0xFFFFFFFF
            return (v % 1000) / 1000.0
        for x in range(w):
            run = 0
            for y in range(h):
                if not self.map[y][x]:
                    run = 0
                    continue
                run += 1
                dp = run
                n1 = cheap_noise(x, y, 0)
                n2 = cheap_noise(x, y, 999)
                shade = 0.82 + (n1 * 0.6 + n2 * 0.4) * 0.36
                deep_fade = max(0.55, 1.0 - max(0, dp - grass_h * 3) * 0.004)
                rockness = min(1.0, max(0.0, (dp - grass_h * 2) / max(1.0, h * 0.35)))
                tip = 1.0 if dp <= 2 else 0.94
                is_grass = dp <= grass_h
                if is_grass:
                    r0, g0, b0 = self.color[0] * tip, self.color[1] * tip, self.color[2] * tip
                else:
                    br_, bg_, bb_ = self.dirt_color
                    r0 = br_ * (1 - rockness) + 105 * rockness
                    g0 = bg_ * (1 - rockness) + 98 * rockness
                    b0 = bb_ * (1 - rockness) + 92 * rockness
                    if n2 > 0.78 and rockness > 0.3:
                        r0 += 28; g0 += 26; b0 += 24
                k = shade * deep_fade
                r0 *= k; g0 *= k; b0 *= k
                left_edge = x > 0 and self.map[y][x] and not self.map[y][max(0, x - 1)]
                right_edge = x < w - 1 and self.map[y][x] and not self.map[y][min(w - 1, x + 1)]
                if left_edge:
                    r0 += 18; g0 += 16; b0 += 12
                if right_edge:
                    r0 *= 0.8; g0 *= 0.8; b0 *= 0.8
                below_solid = y < h - 1 and self.map[min(y + 1, h - 1)][x]
                if not below_solid and dp > grass_h:
                    r0 *= 0.6; g0 *= 0.6; b0 *= 0.6
                r = int(max(0, min(255, r0)))
                g = int(max(0, min(255, g0)))
                b = int(max(0, min(255, b0)))
                self.surface.set_at((x, y), (r, g, b, 255))

        # ★ Травиночки и цветы поверх кромки
        for dec in self.decorations:
            if dec[0] == 'grass':
                _, dx, dy, hgt = dec
                if dy < self.height and not self.map[dy][dx]:
                    sway = math.sin((dx + self.seed % 100) * 0.3) * 1.5
                    gc = (random.Random(dx * 7 + dy).choice([(50, 150, 55), (70, 170, 65), (90, 185, 80)]))
                    pygame.draw.line(self.surface, gc, (dx, dy + 1), (dx - 2 + sway, dy - hgt), 1)
                    pygame.draw.line(self.surface, gc, (dx, dy + 1), (dx + 2 + sway, dy - hgt + 1), 1)
            elif dec[0] == 'rock':
                _, dx, dy, s = dec
                if dy - s > 0 and not self.map[dy - s][dx]:
                    pygame.draw.circle(self.surface, (130, 122, 112), (dx, dy - s // 2), s)
                    pygame.draw.circle(self.surface, (165, 158, 148), (dx - s // 3, dy - s // 2 - s // 3), max(1, s // 2))
            elif dec[0] == 'flower':
                _, dx, dy, c = dec
                if dy - 5 > 0 and not self.map[dy - 5][dx]:
                    pygame.draw.line(self.surface, (50, 130, 50), (dx, dy), (dx, dy - 4), 1)
                    for pa in range(0, 360, 72):  # ★ лепестки
                        ar = math.radians(pa)
                        pygame.draw.circle(self.surface, c,
                                           (int(dx + math.cos(ar) * 2), int(dy - 5 + math.sin(ar) * 2)), 1)
                    pygame.draw.circle(self.surface, (255, 240, 120), (dx, dy - 5), 1)
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

        t = pygame.time.get_ticks() / 200
        breathe = math.sin(t * 1.3 + self.x * 0.05) * 0.7  # ★ дыхание в простое

        if self.parachute:
            sw = math.sin(t) * 2
            pc = tuple(min(255, c + 60) for c in self.color)
            pygame.draw.arc(surface, pc, (sx - 19 + sw, sy - 39, 38, 26), 0, math.pi, 4)
            pygame.draw.arc(surface, (255, 255, 255), (sx - 19 + sw, sy - 39, 38, 26), 0.3, math.pi - 0.3, 1)
            pygame.draw.line(surface, (220, 220, 220), (sx - 14 + sw, sy - 18), (sx, sy - 5), 1)
            pygame.draw.line(surface, (220, 220, 220), (sx + 14 + sw, sy - 18), (sx, sy - 5), 1)

        lo = math.sin(self.walk_frame * math.pi / 2) * 3
        if self.on_ground:
            pygame.draw.rect(surface, (60, 60, 60), (sx - 6, sy + 10, 4, 8 + lo))
            pygame.draw.rect(surface, (40, 40, 40), (sx - 7, sy + 17 + lo, 6, 3))
            pygame.draw.rect(surface, (60, 60, 60), (sx + 2, sy + 10, 4, 8 - lo))
            pygame.draw.rect(surface, (40, 40, 40), (sx + 1, sy + 17 - lo, 6, 3))
        else:
            pygame.draw.rect(surface, (60, 60, 60), (sx - 5, sy + 8, 4, 6))
            pygame.draw.rect(surface, (60, 60, 60), (sx + 1, sy + 8, 4, 6))

        # ★ Тело с градиентом: база + тёмный низ + светлый верх-блик
        body = (sx - 8, sy - 5, 16, 20 + int(breathe))
        pygame.draw.ellipse(surface, self.color, body)
        dark_c = tuple(max(0, c - 55) for c in self.color)
        light_c = tuple(min(255, c + 55) for c in self.color)
        pygame.draw.ellipse(surface, dark_c, (sx - 7, sy + 5, 14, 9))
        pygame.draw.ellipse(surface, light_c, (sx - 5, sy - 4, 10, 7))
        pygame.draw.ellipse(surface, dark_c, body, 2)  # контур

        # ★ Базука/палка с направлением и колёсиком прицела
        gun_y = sy - 3 + int(math.sin(self.angle) * 4)
        if self.direction == 1:
            pygame.draw.line(surface, (255, 213, 176), (sx + 5, sy), (sx + 12, gun_y), 3)
            pygame.draw.rect(surface, (90, 90, 95), (sx + 10, gun_y - 3, 10, 4))
            pygame.draw.rect(surface, (55, 55, 60), (sx + 10, gun_y - 3, 10, 4), 1)
            pygame.draw.circle(surface, (140, 140, 150), (sx + 11, gun_y - 1), 2)
        else:
            pygame.draw.line(surface, (255, 213, 176), (sx - 5, sy), (sx - 12, gun_y), 3)
            pygame.draw.rect(surface, (90, 90, 95), (sx - 20, gun_y - 3, 10, 4))
            pygame.draw.rect(surface, (55, 55, 60), (sx - 20, gun_y - 3, 10, 4), 1)
            pygame.draw.circle(surface, (140, 140, 150), (sx - 11, gun_y - 1), 2)

        # ★ Голова с бликом + берёт командного цвета
        hc = (255, 213, 176)
        pygame.draw.circle(surface, hc, (sx, sy - 12), 9)
        pygame.draw.circle(surface, (255, 235, 210), (sx - 3, sy - 15), 3)
        pygame.draw.circle(surface, tuple(max(0, c - 60) for c in hc), (sx, sy - 12), 9, 1)
        pygame.draw.arc(surface, self.color, (sx - 9, sy - 21, 18, 12), 0, math.pi, 3)
        pygame.draw.arc(surface, tuple(min(255, c + 50) for c in self.color), (sx - 9, sy - 22, 18, 12), 0.4,
                        math.pi - 0.4, 1)
        ex = sx + self.direction * 3
        pygame.draw.circle(surface, (255, 255, 255), (ex - 2, sy - 14), 3)
        pygame.draw.circle(surface, (255, 255, 255), (ex + 2, sy - 14), 3)
        pygame.draw.circle(surface, (0, 0, 0), (ex - 2 + self.direction, sy - 14), 1)
        pygame.draw.circle(surface, (0, 0, 0), (ex + 2 + self.direction, sy - 14), 1)
        # ★ Рот-улыбка по направлению
        pygame.draw.arc(surface, (120, 70, 50), (ex - 4, sy - 10, 8, 6), math.pi, math.pi * 2, 1)

        if self.health < 100:
            bw, hw = 26, int(26 * self.health / 100)
            pygame.draw.rect(surface, (0, 0, 0), (sx - 13, sy - 30, bw + 2, 6))
            hc2 = (0, 200, 0) if self.health > 50 else (255, 165, 0) if self.health > 25 else (255, 0, 0)
            pygame.draw.rect(surface, hc2, (sx - 12, sy - 29, hw, 4))
            pygame.draw.rect(surface, tuple(min(255, c + 80) for c in hc2), (sx - 12, sy - 29, hw, 1))

        if is_active:
            b = math.sin(pygame.time.get_ticks() / 200) * 3
            pts = [(sx, sy - 38 + b), (sx - 6, sy - 46 + b), (sx + 6, sy - 46 + b)]
            pygame.draw.polygon(surface, (255, 215, 0), pts)
            pygame.draw.polygon(surface, (255, 255, 180), [(sx - 2, sy - 40 + b), (sx - 5, sy - 45 + b),
                                                           (sx + 1, sy - 44 + b)])
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
    terrain = TerrainMap(width, height, (95, 165, 70), (65, 100, 45), (121, 84, 55))
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
    terrain = TerrainMap(width, height, (90, 170, 78), (60, 110, 50), (115, 82, 52))
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
    terrain = TerrainMap(width, height, (150, 140, 95), (85, 75, 50), (118, 92, 60))
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
     "terrain_color": (85, 130, 65), "sky_top": (24, 52, 128), "sky_bottom": (140, 195, 245),
     "dirt_color": (121, 84, 55), "mountain_far": (70, 90, 140), "mountain_near": (52, 74, 112)},
    {"name": "Islands", "desc": "Three close islands", "generator": generate_islands,
     "terrain_color": (80, 140, 70), "sky_top": (16, 36, 96), "sky_bottom": (95, 175, 240),
     "dirt_color": (115, 82, 52), "mountain_far": (60, 88, 130), "mountain_near": (45, 70, 105)},
    {"name": "Valley", "desc": "Hills with valley", "generator": generate_valley,
     "terrain_color": (110, 100, 70), "sky_top": (52, 32, 96), "sky_bottom": (200, 150, 190),
     "dirt_color": (118, 92, 60), "mountain_far": (105, 80, 130), "mountain_near": (80, 58, 105)},
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


class ExplosionFX:
    """★ Красивые многослойные взрывы: вспышка, огненный шар, ударная волна, дым, искры, воронка."""

    def __init__(self, x, y, radius, parts=None):
        self.x, self.y, self.r = x, y, radius
        self.t = 0
        self.duration = 48
        self.flash_r = radius * 3.2
        self.wave_r = radius * 2.6
        self.smoke = []
        rng = random.Random(int(x * 131 + y))
        for i in range(max(8, int(radius / 3))):
            a = rng.uniform(0, math.pi * 2)
            sp = rng.uniform(0.4, 1.8)
            self.smoke.append({'x': x + rng.uniform(-radius * 0.4, radius * 0.4),
                               'y': y + rng.uniform(-radius * 0.4, radius * 0.4),
                               'vx': math.cos(a) * sp, 'vy': math.sin(a) * sp - rng.uniform(0.5, 1.6),
                               'r': rng.uniform(radius * 0.18, radius * 0.5),
                               'delay': rng.randint(0, 10)})
        self.sparks = []
        for i in range(max(10, int(radius / 2))):
            a = rng.uniform(0, math.pi * 2)
            sp = rng.uniform(2.5, 7.0)
            self.sparks.append({'x': x, 'y': y, 'vx': math.cos(a) * sp, 'vy': math.sin(a) * sp - 1.5,
                                'life': rng.randint(18, 34)})
        # Осколки породы летят в игровую систему частиц
        if parts is not None:
            for i in range(max(6, int(radius / 4))):
                a = rng.uniform(math.pi, math.pi * 2)
                sp = rng.uniform(2, 6)
                parts.append({'x': x, 'y': y, 'vx': math.cos(a) * sp, 'vy': math.sin(a) * sp,
                              'life': rng.randint(25, 45),
                              'color': rng.choice([(90, 70, 50), (120, 95, 65), (70, 55, 40), (140, 120, 90)])})

    def update(self):
        self.t += 1
        for s in self.smoke:
            if self.t > s['delay']:
                s['x'] += s['vx']; s['y'] += s['vy']; s['vy'] -= 0.015; s['vx'] *= 0.985; s['r'] += 0.55
        for p in self.sparks:
            p['x'] += p['vx']; p['y'] += p['vy']; p['vy'] += 0.25; p['vx'] *= 0.97; p['life'] -= 1
        return self.t < self.duration

    def draw(self, surface, cam_x, cam_y):
        k = self.t / self.duration
        sx, sy = int(self.x - cam_x), int(self.y - cam_y)
        layer = _additive_layer(surface.get_size())

        # ★ Воронка — тёмное кольцо кратера (мультипликативно)
        if k < 0.6:
            crater_a = int(120 * (1 - k / 0.6))
            cs = pygame.Surface((int(self.r * 2.2), int(self.r * 2.2)), pygame.SRCALPHA)
            pygame.draw.circle(cs, (40, 30, 25, crater_a), cs.get_rect().center, int(self.r * 1.05))
            pygame.draw.circle(cs, (0, 0, 0, 0), cs.get_rect().center, int(self.r * 0.55))
            ring = pygame.Surface(cs.get_size(), pygame.SRCALPHA)
            pygame.draw.circle(ring, (25, 15, 10, crater_a), ring.get_rect().center, int(self.r * 1.05),
                               max(2, int(self.r * 0.18)))
            cs.blit(ring, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
            surface.blit(cs, (sx - cs.get_width() // 2, sy - cs.get_height() // 2))

        # ★ Вспышка (первые кадры)
        if self.t < 8:
            fk = 1 - self.t / 8
            glow_dot(layer, sx, sy, self.flash_r * (0.4 + fk * 0.6), (255, 230, 160), int(255 * fk))
        # ★ Огненный шар сжимается к центру и гаснет
        if k < 0.55:
            fire_k = k / 0.55
            fr = self.r * (1.35 - fire_k * 0.9)
            glow_dot(layer, sx, sy, fr, (255, 90, 20), int(230 * (1 - fire_k)))
            glow_dot(layer, sx, sy, fr * 0.6, (255, 200, 60), int(240 * (1 - fire_k)))
            glow_dot(layer, sx, sy, fr * 0.3, (255, 255, 220), int(250 * (1 - fire_k)))
        # ★ Ударная волна — расходящееся кольцо
        if k < 0.7:
            wk = k / 0.7
            wr = self.wave_r * wk
            alpha = int(200 * (1 - wk))
            rad = max(2, int(wr * 2))
            ws = pygame.Surface((rad, rad), pygame.SRCALPHA)
            pygame.draw.circle(ws, (255, 240, 210, alpha), (rad // 2, rad // 2), rad // 2,
                               max(1, int(6 * (1 - wk))))
            layer.blit(ws, (sx - rad // 2, sy - rad // 2), special_flags=pygame.BLEND_PREMULTIPLIED)
        # ★ Искры-светлячки
        for p in self.sparks:
            if p['life'] > 0:
                glow_dot(layer, p['x'] - cam_x, p['y'] - cam_y, 3, (255, 190, 90), min(255, p['life'] * 9))
        surface.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        # ★ Дым — обычный альфа-слой поверх
        if k > 0.12:
            ds = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            for s in self.smoke:
                if self.t > s['delay']:
                    dk = min(1.0, (self.t - s['delay']) / (self.duration - s['delay']))
                    da = int(110 * (1 - dk))
                    gray = 70 + int(dk * 60)
                    dr = max(2, int(s['r']))
                    dsm = pygame.Surface((dr * 2, dr * 2), pygame.SRCALPHA)
                    pygame.draw.circle(dsm, (gray, gray, gray, da), (dr, dr), dr)
                    ds.blit(dsm, (int(s['x'] - cam_x) - dr, int(s['y'] - cam_y) - dr))
            surface.blit(ds, (0, 0))


def draw_trail(surface, trail, color, cam_x, cam_y):
    if len(trail) < 2: return
    layer = _additive_layer(surface.get_size())
    for i in range(1, len(trail)):
        alpha = i / len(trail)
        c = tuple(int(color[j] * alpha) for j in range(3))
        thickness = max(1, int(3 * alpha))
        pygame.draw.line(surface, c,
                         (int(trail[i - 1][0] - cam_x), int(trail[i - 1][1] - cam_y)),
                         (int(trail[i][0] - cam_x), int(trail[i][1] - cam_y)), thickness)
        if i % 3 == 0:
            glow_dot(layer, int(trail[i][0] - cam_x), int(trail[i][1] - cam_y), 5 * alpha + 2, color,
                     int(90 * alpha))
    surface.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


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


def make_sky_surface(width, height, sky_top, sky_bottom):
    """★ Небо: вертикальный градиент + лёгкий у-шум + звёзды в верхней части."""
    sky = pygame.Surface((width, height))
    for y in range(height):
        r = y / height
        # Нелинейный градиент — сверху насыщеннее
        rr = r ** 0.85
        c = (int(sky_top[0] * (1 - rr) + sky_bottom[0] * rr),
             int(sky_top[1] * (1 - rr) + sky_bottom[1] * rr),
             int(sky_top[2] * (1 - rr) + sky_bottom[2] * rr))
        pygame.draw.line(sky, c, (0, y), (width, y))
    rng = random.Random(42)
    for _ in range(int(width * height / 9000)):
        sxp, syp = rng.randint(0, width - 1), rng.randint(0, int(height * 0.55))
        br = rng.randint(120, 235)
        sz = 1 if rng.random() < 0.7 else 2
        pygame.draw.circle(sky, (br, br, min(255, br + 20)), (sxp, syp), sz)
    return sky


def draw_mountains_parallax(surface, cam_x, layer_seed, base_y, color, scale_x, height_amp):
    """★ Дальние горы с параллаксом (рисуются за terrain)."""
    rng = random.Random(layer_seed)
    pts = [(x, base_y - abs(math.sin(x * 0.004 + layer_seed) * height_amp
                            + math.sin(x * 0.011 + layer_seed * 2) * height_amp * 0.5)
            - rng.random() * 6)
           for x in range(-100, SCREEN_W + 101, 24)]
    shifted = [(px - cam_x * scale_x, py) for px, py in pts]
    poly = shifted + [(SCREEN_W + 100, surface.get_height()), (-100, surface.get_height())]
    pygame.draw.polygon(surface, color, poly)


def draw_clouds(surface, cam_x, cam_y, t):
    """★ Объёмные облака с тенью и параллаксом (2 слоя)."""
    for speed, scale_x, alpha_c, shadow_c, lst in [
            (8, 1.0, (255, 255, 255), (210, 220, 235),
             [(100, 50, 80), (400, 80, 60), (700, 40, 90), (1000, 70, 70), (1300, 50, 85)]),
            (14, 1.0, (235, 240, 250), (195, 205, 225),
             [(250, 120, 55), (850, 130, 65), (1150, 110, 50)])]:
        for bx, by, sz in lst:
            cx = ((bx + t * speed) % (WIDTH + 200)) - 100 - int(cam_x * scale_x)
            cy = by - int(cam_y * 0.5)
            if -150 < cx < SCREEN_W + 50:
                # тень снизу
                pygame.draw.ellipse(surface, shadow_c, (cx, cy + 4, sz, sz // 2))
                pygame.draw.ellipse(surface, shadow_c, (cx + sz // 3, cy - sz // 4 + 4, sz // 2, sz // 2))
                # тело
                pygame.draw.ellipse(surface, alpha_c, (cx, cy, sz, sz // 2))
                pygame.draw.ellipse(surface, alpha_c, (cx + sz // 3, cy - sz // 4, sz // 2, sz // 2))
                # блик сверху
                hl = tuple(min(255, c + 0) for c in (255, 255, 255))
                pygame.draw.ellipse(surface, hl, (cx + sz // 6, cy - 2, sz // 2, sz // 4))


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

    sky = make_sky_surface(WIDTH, HEIGHT, st, sb)
    # ★ Скроллящийся декоративный слой: силуэты дальних холмов + деревья на горизонте
    scroll_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _rng = random.Random(7)
    for hx in range(0, WIDTH, 60):
        hy = int(HEIGHT * 0.52 + math.sin(hx * 0.012 + 2) * 45 + _rng.uniform(-8, 8))
        pygame.draw.ellipse(scroll_surf, (40, 62, 92, 170), (hx - 90, hy, 220, 160))
    for tx in range(40, WIDTH, 90):
        ty = int(HEIGHT * 0.58 + math.sin(tx * 0.02) * 25)
        if _rng.random() < 0.7:
            pygame.draw.rect(scroll_surf, (28, 44, 60, 200), (tx, ty, 4, 14))
            pygame.draw.circle(scroll_surf, (34, 66, 48, 200), (tx + 2, ty - 4), 11)

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
    return terrain, sp, sky, scroll_surf, teams, worms, nt, loadout, sm


def main():
    terrain, spawn_points, sky, scroll_surf, teams, worms, num_teams, loadout, map_data = reset_game()

    ct, cwi = 0, 0
    phase = 'aiming'
    power = 0.0
    wind = random.uniform(-0.08, 0.08)
    projs, parts, dtexts = [], [], []
    fxs = []  # ★ Эффекты взрывов
    shake = {'t': 0, 'mag': 0}  # ★ Тряска камеры
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
        fxs.append(ExplosionFX(cx, cy, br, parts))
        shake['t'] = max(shake['t'], min(18, 6 + br / 8))  # ★ Тряска камеры от взрыва

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
        fxs = [fx for fx in fxs if fx.update()]
        if shake['t'] > 0: shake['t'] -= 1
        for p in parts: p['x'] += p['vx']; p['y'] += p['vy']; p['vy'] += 0.1; p['life'] -= 1
        parts = [p for p in parts if p['life'] > 0]
        for d in dtexts: d['y'] -= 0.5; d['life'] -= 1
        dtexts = [d for d in dtexts if d['life'] > 0]

        if phase == 'waiting' and not projs:
            at = set(w.team for w in worms if w.alive)
            if len(at) <= 1:
                winner = list(at)[0] if at else None
                show_victory_screen(winner, teams)
                terrain, spawn_points, sky, scroll_surf, teams, worms, num_teams, loadout, map_data = reset_game()
                ct, cwi, phase = 0, 0, 'aiming'
                projs, parts, dtexts, fxs = [], [], [], []
                shake['t'] = 0
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
        sx_off = sy_off = 0
        if shake['t'] > 0:  # ★ Тряска камеры
            m = shake['t'] * 0.55
            sx_off = random.uniform(-m, m); sy_off = random.uniform(-m, m)
        scr = scroll_surf.get_rect()
        scr.x = -(int(cam_x * 0.4) % WIDTH); scr.y = -(int(cam_y * 0.4) % HEIGHT)
        for dx in range(0, SCREEN_W + WIDTH, WIDTH):
            for dy in range(0, SCREEN_H + HEIGHT, HEIGHT):
                screen.blit(scroll_surf, (scr.x + dx, scr.y + dy))
        # ★ Дальние горы (параллакс)
        base_my = WATER_LEVEL - int(cam_y * 0.55) + 40
        draw_mountains_parallax(screen, cam_x, 3.7, base_my, map_data['mountain_far'], 0.35, 130)
        draw_mountains_parallax(screen, cam_x, 8.2, base_my + 35, map_data['mountain_near'], 0.55, 90)
        draw_clouds(screen, cam_x, cam_y, pygame.time.get_ticks() / 1000)
        sun_x, sun_y = 100 - int(cam_x * 0.4), 60 - int(cam_y * 0.4)
        if -80 < sun_x < SCREEN_W + 80:
            pulse = 1 + math.sin(pygame.time.get_ticks() / 900) * 0.06
            draw_glow_circle(screen, (sun_x, sun_y), int(75 * pulse), (255, 210, 90), core_alpha=90)
            pygame.draw.circle(screen, (255, 246, 190), (sun_x, sun_y), 26)
            pygame.draw.circle(screen, (255, 255, 235), (sun_x - 6, sun_y - 6), 12)

        wsy = WATER_LEVEL - int(cam_y)
        if wsy < SCREEN_H:
            t = pygame.time.get_ticks() / 1000
            wtop = max(0, wsy)
            wat = pygame.Surface((SCREEN_W, max(1, SCREEN_H - wtop)), pygame.SRCALPHA)
            for x in range(0, SCREEN_W, 4):
                wo = math.sin((x + cam_x) * 0.03 + t * 2) * 3 + math.sin((x + cam_x) * 0.011 - t * 1.3) * 2
                wy = wsy + wo
                d = min(80, SCREEN_H - int(wy))
                if d > 0:
                    yy = int(wy) - wsy
                    pygame.draw.line(wat, (30, 120, 210, 150), (x, yy), (x, yy + min(6, d)))
                    if d > 6:
                        pygame.draw.rect(wat, (0, 45, 120, 215), (x, yy + 6, 4, d - 6))
                    foam = 0.5 + 0.5 * math.sin((x + cam_x) * 0.08 + t * 3.5)  # ★ пенная кромка
                    if foam > 0.75:
                        pygame.draw.line(wat, (225, 245, 255, int(120 * foam)), (x, yy), (x, yy + 2))
            screen.blit(wat, (0, wtop))

        screen.blit(terrain.get_surface(), (-int(cam_x), -int(cam_y)))

        for p in projs:
            if p.type not in ('mine',):
                tc = WEAPONS.get(p.type, {}).get('trail_color', (255, 200, 100))
                draw_trail(screen, p.trail, tc, cam_x, cam_y)

        for p in projs:
            sx, sy = int(p.x - cam_x), int(p.y - cam_y)
            if sx < -20 or sx > SCREEN_W + 20 or sy < -20 or sy > SCREEN_H + 20: continue
            if p.type == 'mine' and p.active:
                pygame.draw.circle(screen, (95, 95, 100), (sx, sy), 6)
                pygame.draw.circle(screen, (150, 150, 158), (sx - 2, sy - 2), 2)
                pygame.draw.circle(screen, (255, 0, 0), (sx, sy), 6, 1)
                if p.armed:
                    blink = pygame.time.get_ticks() % 500 < 250
                    if blink:
                        draw_glow_circle(screen, (sx, sy), 14, (255, 40, 40), core_alpha=170)
                    pygame.draw.circle(screen, (255, 60, 60) if blink else (140, 20, 20), (sx, sy - 7), 2)
                else:
                    pr = 1 - p.arm_timer / 90
                    pygame.draw.arc(screen, (0, 255, 0), (sx - 8, sy - 8, 16, 16), -math.pi / 2,
                                    -math.pi / 2 + pr * math.pi * 2, 2)
            elif p.type == 'air_strike':
                ang = math.atan2(p.vy, p.vx)
                hb = pygame.Surface((14, 8), pygame.SRCALPHA)
                pygame.draw.ellipse(hb, (70, 72, 78), (0, 1, 13, 6))
                pygame.draw.polygon(hb, (95, 98, 105), [(1, 1), (5, 0), (5, 3)])
                pygame.draw.circle(hb, (255, 120, 60), (1, 4), 2)
                screen.blit(pygame.transform.rotozoom(hb, -math.degrees(ang), 1.0), (sx - 8, sy - 5))
                draw_glow_circle(screen, (sx - int(math.cos(ang) * 8), sy - int(math.sin(ang) * 8)),
                                 6, (255, 140, 50), core_alpha=150)
            elif p.type == 'banana':
                rot = pygame.time.get_ticks() / 8 % 360
                bs = pygame.Surface((18, 18), pygame.SRCALPHA)
                pygame.draw.arc(bs, (255, 220, 60), (2, 2, 14, 14), math.pi * 0.15, math.pi * 0.95, 5)
                pygame.draw.arc(bs, (255, 245, 150), (2, 2, 14, 14), math.pi * 0.3, math.pi * 0.8, 2)
                pygame.draw.circle(bs, (120, 90, 30), (4, 12), 2)
                screen.blit(pygame.transform.rotate(bs, rot), (sx - 9, sy - 9))
                draw_glow_circle(screen, (sx, sy), 12, (255, 240, 80), core_alpha=110)
            elif p.type == 'grenade':
                pygame.draw.circle(screen, (55, 58, 55), (sx, sy), 5)
                pygame.draw.circle(screen, (110, 115, 110), (sx - 1, sy - 1), 2)
                pygame.draw.rect(screen, (90, 90, 80), (sx - 1, sy - 7, 3, 3))
                if p.timer < 60 and pygame.time.get_ticks() % 200 < 100:
                    draw_glow_circle(screen, (sx, sy), 11, (255, 60, 30), core_alpha=190)
            else:
                ang = math.atan2(p.vy, p.vx)
                rb = pygame.Surface((16, 6), pygame.SRCALPHA)
                pygame.draw.ellipse(rb, (120, 122, 128), (0, 0, 16, 6))
                pygame.draw.rect(rb, (70, 72, 78), (0, 1, 5, 4))
                pygame.draw.circle(rb, (255, 200, 120), (14, 3), 2)
                screen.blit(pygame.transform.rotate(rb, -math.degrees(ang)), (sx - 8, sy - 3))
                draw_glow_circle(screen, (sx + int(math.cos(ang) * 6), sy + int(math.sin(ang) * 6)),
                                 7, (255, 170, 70), core_alpha=170)

        glow_layer = _additive_layer((SCREEN_W, SCREEN_H))
        for p in parts:
            sx, sy = int(p['x'] - cam_x), int(p['y'] - cam_y)
            if -10 < sx < SCREEN_W + 10 and -10 < sy < SCREEN_H + 10:
                sz = max(1, int(3 * p['life'] / 30))
                pygame.draw.circle(screen, p['color'], (sx, sy), sz)
                glow_dot(glow_layer, sx, sy, sz * 3, p['color'], min(200, p['life'] * 7))
        screen.blit(glow_layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        for fx in fxs:  # ★ Многослойные взрывы поверх сцены
            fx.draw(screen, cam_x, cam_y)

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
                # ★ Пунктир продолжения + пульсирующая точка прицела
                vx, vy = math.cos(aw.angle) * aw.direction, math.sin(aw.angle)
                for dd in range(int(l) + 8, int(l) + 130, 10):
                    if (dd - int(l)) % 20 < 10:
                        pygame.draw.circle(screen, (230, 230, 230), (sx + int(vx * dd), sy + int(vy * dd)), 1)
                tx_, ty_ = sx + int(vx * (l + 140)), sy + int(vy * (l + 140))
                rr = 3 + math.sin(pygame.time.get_ticks() / 40) * 1.2
                pygame.draw.circle(screen, (255, 70, 70), (tx_, ty_), max(1, int(rr)), 1)
                pygame.draw.circle(screen, (255, 70, 70), (tx_, ty_), 1)
            elif wp['type'] in ('hitscan', 'shotgun'):
                l = 200
                ex = sx + int(math.cos(aw.angle) * l * aw.direction);
                ey = sy + int(math.sin(aw.angle) * l)
                gl = _additive_layer((SCREEN_W, SCREEN_H))
                glow_dot(gl, ex, ey, 8, (255, 60, 60), core_alpha=120)
                seg = 6
                for i in range(0, l, seg * 2):
                    x1 = sx + int(math.cos(aw.angle) * i * aw.direction)
                    y1 = sy + int(math.sin(aw.angle) * i)
                    x2 = sx + int(math.cos(aw.angle) * min(i + seg, l) * aw.direction)
                    y2 = sy + int(math.sin(aw.angle) * min(i + seg, l))
                    pygame.draw.line(screen, (255, 50, 50), (x1, y1), (x2, y2), 1)
                screen.blit(gl, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        if sx_off or sy_off:
            screen.scroll(sx_off, sy_off)  # ★ Тряска: сдвигаем мир, HUD остаётся стабильным

        font = pygame.font.Font(None, 22);
        fs = pygame.font.Font(None, 16)
        # ★ Полупрозрачные панели HUD
        hud = pygame.Surface((SCREEN_W, 48), pygame.SRCALPHA)
        hud.fill((8, 10, 22, 195))
        screen.blit(hud, (0, 0))
        pygame.draw.line(screen, tuple(min(255, c + 60) for c in teams[ct]['color']), (0, 47), (SCREEN_W, 47), 2)
        pygame.draw.rect(screen, teams[ct]['color'], (10, 8, 28, 28), border_radius=6)
        pygame.draw.rect(screen, (255, 255, 255), (10, 8, 28, 28), 2, border_radius=6)
        screen.blit(font.render(teams[ct]['name'], True, (255, 255, 255)), (45, 10))
        tc = (255, 100, 100) if timer // 60 < 10 else (255, 255, 255)
        screen.blit(font.render(f"Time: {timer // 60}s", True, tc), (SCREEN_W // 2 - 40, 5))
        wd = '>>>' if wind > 0 else '<<<'
        screen.blit(font.render(f"Wind: {wd}{abs(wind) * 100:.1f}", True, (200, 200, 200)), (SCREEN_W // 2 - 40, 25))
        for t in range(num_teams):
            th = sum(w.health for w in worms if w.team == t and w.alive)
            ac = sum(1 for w in worms if w.team == t and w.alive)
            tx = SCREEN_W - 170;
            ty = 6 + t * 14
            pygame.draw.rect(screen, TEAM_COLORS[t], (tx, ty, 8, 8), border_radius=2)
            barw = int(60 * th / max(1, 300))
            pygame.draw.rect(screen, (40, 40, 55), (tx + 52, ty + 1, 60, 6), border_radius=3)
            if barw > 0:
                pygame.draw.rect(screen, TEAM_COLORS[t], (tx + 52, ty + 1, barw, 6), border_radius=3)
            screen.blit(fs.render(f"{th}hp ({ac})", True, (200, 200, 200)), (tx + 12, ty - 2))

        py_h = SCREEN_H - 50
        panel = pygame.Surface((SCREEN_W, 50), pygame.SRCALPHA)
        panel.fill((8, 10, 22, 205))
        screen.blit(panel, (0, py_h))
        pygame.draw.line(screen, (90, 100, 150), (0, py_h), (SCREEN_W, py_h), 1)
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
            pygame.draw.rect(screen, (85, 90, 140) if sel else (52, 55, 78), (wx, wy, 90, 40), border_radius=7)
            if sel:
                pygame.draw.rect(screen, (255, 215, 0), (wx, wy, 90, 40), 2, border_radius=7)
            nc = (255, 255, 255) if am != 0 else (100, 100, 100)
            screen.blit(fs.render(f"{i + 1}:{wd['name'][:8]}", True, nc), (wx + 4, wy + 2))
            at = "inf" if am == -1 else f"x{am}" if am > 0 else "empty"
            ac = (100, 255, 100) if am == -1 else (255, 200, 0) if am > 0 else (255, 80, 80)
            screen.blit(fs.render(at, True, ac), (wx + 4, wy + 18))
            if sel: screen.blit(fs.render(wd['desc'], True, (200, 200, 200)), (wx, wy - 14))
        screen.blit(fs.render("[TAB]Switch [J]Jump [1-8]Weapon [SPACE]Fire [arrows]Aim/Climb", True, (130, 130, 130)),
                    (10, py_h + 36))

        if phase == 'power':
            pygame.draw.rect(screen, (30, 30, 40), (SCREEN_W // 2 - 62, 52, 124, 16), border_radius=8)
            pygame.draw.rect(screen, (120, 120, 140), (SCREEN_W // 2 - 62, 52, 124, 16), 1, border_radius=8)
            bw = int(power / 100 * 120)
            pc_bar = pygame.Surface((120, 12), pygame.SRCALPHA)
            for xx in range(bw):
                frac = xx / 120
                colr = (int(255 * min(1, frac * 2)), int(255 * min(1, (1 - frac) * 2 + 0.4)), 40)
                pygame.draw.line(pc_bar, (*colr, 235), (xx, 0), (xx, 11))
            screen.blit(pc_bar, (SCREEN_W // 2 - 60, 54))
            pygame.draw.line(screen, (255, 255, 255), (SCREEN_W // 2 - 61 + bw, 52),
                             (SCREEN_W // 2 - 61 + bw, 68), 2)

        for d in dtexts:
            sx, sy = int(d['x'] - cam_x), int(d['y'] - cam_y)
            kf = d['life'] / d['max_life']  # 1 -> 0
            pop = 1.4 if kf > 0.9 else 1.0 + 0.25 * math.sin(kf * 12)
            tf = pygame.font.Font(None, max(12, int(20 * pop)))
            txt = tf.render(d['text'], True, d['color'])
            shd = tf.render(d['text'], True, (0, 0, 0))
            a = min(255, int(255 * min(1.0, kf * 2.5)))
            txt.set_alpha(a); shd.set_alpha(a)
            screen.blit(shd, (sx - shd.get_width() // 2 + 1, sy + 1))
            screen.blit(txt, (sx - txt.get_width() // 2, sy))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()