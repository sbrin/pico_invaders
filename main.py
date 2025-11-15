from machine import Pin, I2C
from utime import sleep_ms, ticks_ms, ticks_diff, ticks_add
import sys
import framebuf
from urandom import getrandbits
from ssd1306 import SSD1306_I2C
from rotary_irq_rp2 import RotaryIRQ

PIX_RES_X = 128
PIX_RES_Y = 64

# Rotary encoder wiring: CLK -> GP21, DT -> GP20, SW -> GP22
CLK_PIN = 21
DT_PIN = 20
SW_PIN = 22

BUTTON_DEBOUNCE_MS = 40
ENCODER_INCREMENT = 2
ENCODER_REVERSE = False  # Set to True to reverse direction

encoder = RotaryIRQ(
    pin_num_clk=CLK_PIN,
    pin_num_dt=DT_PIN,
    min_val=0,
    max_val=0,  # Unbounded range
    incr=ENCODER_INCREMENT,
    reverse=ENCODER_REVERSE,
    range_mode=RotaryIRQ.RANGE_UNBOUNDED,
    pull_up=True,
    half_step=True,
    invert=False
)
encoder_sw = Pin(SW_PIN, Pin.IN, Pin.PULL_UP)

last_reported_position = encoder.value()
last_button_state = encoder_sw.value()
last_button_time = ticks_ms()

# OLED display setup
SCL_PIN = 19
SDA_PIN = 18

i2c_dev = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=200000)
i2c_addr = [hex(ii) for ii in i2c_dev.scan()]
if i2c_addr == []:
    print("No I2C Display Found")
    sys.exit()
else:
    print("I2C Address      : {}".format(i2c_addr[0]))
    print("I2C Configuration: {}".format(i2c_dev))
display = SSD1306_I2C(PIX_RES_X, PIX_RES_Y, i2c_dev)

# assets
image_crab_bits = bytearray(b" \x80\x11\x00?\x80n\xc0\xff\xe0\xbf\xa0\xa0\xa0\x1b\x00")
image_heart_bits = bytearray(b"l\xfe\xfe|8\x10")
image_octopus_bits = bytearray(b"\x0f\x00\x7f\xe0\xff\xf0\xe6p\xff\xf09\xc0f`0\xc0")
image_ship_bits = bytearray(b"\x01\x00\x03\x80\x03\x80\x7f\xfc\xff\xfe\xff\xfe")
image_squid_bits = bytearray(b"\x18<~\xdb\xff$Z\xa5")
image_blast_bits = bytearray(b'\x08\x00\x08\x00D@$\x80\x11\x10\xe0`\x01\x00D\x80\x94\x80\x14@\x22\x00 \x00')


def _make_fb(buffer, width, height):
    return framebuf.FrameBuffer(buffer, width, height, framebuf.MONO_HLSB)


FB_SHIP = _make_fb(image_ship_bits, 15, 6)
FB_CRAB = _make_fb(image_crab_bits, 11, 8)
FB_OCTOPUS = _make_fb(image_octopus_bits, 12, 8)
FB_SQUID = _make_fb(image_squid_bits, 8, 8)
FB_HEART = _make_fb(image_heart_bits, 7, 6)
FB_BLAST = _make_fb(image_blast_bits, 12, 12)
HEART_WIDTH = 7
BLAST_WIDTH = 12
BLAST_HEIGHT = 12

SHIP_WIDTH = 15
SHIP_HEIGHT = 6
SHIP_Y = PIX_RES_Y - SHIP_HEIGHT - 2
SHIP_STEP_PIXELS = 2
SHIP_MIN_X = 0
SHIP_MAX_X = PIX_RES_X - SHIP_WIDTH

PROJECTILE_WIDTH = 1
PROJECTILE_HEIGHT = 4
PROJECTILE_SPEED = 4

HEART_SPACING = 4
HEART_MARGIN = 0
MAX_LIVES = 3
HEART_BLINK_PERIOD_MS = 500

ship_x = (PIX_RES_X - SHIP_WIDTH) // 2
projectile_active = False
projectile_x = 0
projectile_y = 0
score = 0
ship_visible = True
pause_until_ms = None
lives = MAX_LIVES
game_over = False
victory = False

ENEMIES_PER_ROW = 5
ENEMY_COL_SPACING = 20
ENEMY_ROW_START_X = 20
ENEMY_MOVE_INTERVAL_MS = 200
ENEMY_MOVES_BEFORE_FLIP = 10
ENEMY_FIRE_INTERVAL_MS = 3000
ENEMY_PROJECTILE_WIDTH = 1
ENEMY_PROJECTILE_HEIGHT = 4
ENEMY_PROJECTILE_SPEED = 4
PLAYER_HIT_PAUSE_MS = 2000
EXPLOSION_DURATION_MS = 500

enemy_projectile_active = False
enemy_projectile_x = 0
enemy_projectile_y = 0
last_enemy_fire_ms = ticks_ms()
explosions = []
pending_life_loss = False
pending_loss_start_ms = 0

ENEMY_ROW_DEFS = (
    {"name": "squid", "fb": FB_SQUID, "width": 8, "height": 8, "y": 10},
    {"name": "octopus", "fb": FB_OCTOPUS, "width": 12, "height": 8, "y": 22},
    {"name": "crab", "fb": FB_CRAB, "width": 11, "height": 8, "y": 34},
)


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _create_enemy(template, x, y):
    return {
        "name": template["name"],
        "fb": template["fb"],
        "width": template["width"],
        "height": template["height"],
        "x": x,
        "y": y,
        "alive": True,
    }


def _create_enemy_row(row_index, template):
    enemies = []
    for col in range(ENEMIES_PER_ROW):
        x = ENEMY_ROW_START_X + col * ENEMY_COL_SPACING
        enemies.append(_create_enemy(template, x, template["y"]))
    return {
        "row_index": row_index,
        "direction": -1 if row_index % 2 == 0 else 1,
        "moves_since_flip": 5,
        "last_move_ms": ticks_ms(),
        "enemies": enemies,
    }


def _build_enemy_rows():
    return [_create_enemy_row(idx, template) for idx, template in enumerate(ENEMY_ROW_DEFS)]


enemy_rows = _build_enemy_rows()


def _iter_enemies():
    for row in enemy_rows:
        for enemy in row["enemies"]:
            yield enemy


def _alive_enemies():
    return [enemy for enemy in _iter_enemies() if enemy["alive"]]


def _update_enemy_rows(now_ms):
    for row in enemy_rows:
        if ticks_diff(now_ms, row["last_move_ms"]) < ENEMY_MOVE_INTERVAL_MS:
            continue
        row["last_move_ms"] = now_ms
        shift = row["direction"]
        for enemy in row["enemies"]:
            enemy["x"] += shift
        row["moves_since_flip"] += 1
        if row["moves_since_flip"] >= ENEMY_MOVES_BEFORE_FLIP:
            row["direction"] *= -1
            row["moves_since_flip"] = 0


def _rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return not (
        ax + aw <= bx or
        bx + bw <= ax or
        ay + ah <= by or
        by + bh <= ay
    )


def _reset_projectile():
    global projectile_active, projectile_x, projectile_y
    projectile_active = False
    projectile_x = 0
    projectile_y = 0


def _fire_projectile():
    global projectile_active, projectile_x, projectile_y
    if projectile_active:
        return
    projectile_active = True
    projectile_x = ship_x + SHIP_WIDTH // 2
    projectile_y = SHIP_Y - PROJECTILE_HEIGHT


def _update_projectile():
    global projectile_y
    if not projectile_active:
        return
    projectile_y -= PROJECTILE_SPEED
    if projectile_y + PROJECTILE_HEIGHT < 0:
        _reset_projectile()


def _apply_projectile_hits():
    global projectile_active, score
    if not projectile_active:
        return

    for enemy in _iter_enemies():
        if not enemy["alive"]:
            continue
        if _rects_overlap(
            projectile_x,
            projectile_y,
            PROJECTILE_WIDTH,
            PROJECTILE_HEIGHT,
            enemy["x"],
            enemy["y"],
            enemy["width"],
            enemy["height"],
        ):
            enemy["alive"] = False
            projectile_active = False
            score += 1
            blast_x = enemy["x"] + (enemy["width"] - BLAST_WIDTH) // 2
            blast_y = enemy["y"] + (enemy["height"] - BLAST_HEIGHT) // 2
            _spawn_explosion(blast_x, blast_y)
            break
    _check_victory()


def _draw_hearts(now_ms):
    x = PIX_RES_X - HEART_WIDTH - HEART_MARGIN
    for idx in range(lives):
        is_leftmost = idx == lives - 1
        if is_leftmost and pending_life_loss:
            elapsed = ticks_diff(now_ms, pending_loss_start_ms)
            if (elapsed // HEART_BLINK_PERIOD_MS) % 2 == 1:
                x -= HEART_WIDTH + HEART_SPACING
                continue
        display.blit(FB_HEART, x, HEART_MARGIN)
        x -= HEART_WIDTH + HEART_SPACING


def _draw_projectile():
    if not projectile_active:
        return
    draw_y = projectile_y
    draw_height = PROJECTILE_HEIGHT
    if draw_y < 0:
        draw_height += draw_y
        draw_y = 0
    if draw_y >= PIX_RES_Y:
        return
    if draw_y + draw_height > PIX_RES_Y:
        draw_height = PIX_RES_Y - draw_y
    if draw_height > 0:
        display.vline(projectile_x, draw_y, draw_height, 1)


def _draw_enemy_projectile():
    if not enemy_projectile_active:
        return
    draw_y = enemy_projectile_y
    draw_height = ENEMY_PROJECTILE_HEIGHT
    if draw_y < 0:
        draw_height += draw_y
        draw_y = 0
    if draw_y >= PIX_RES_Y:
        return
    if draw_y + draw_height > PIX_RES_Y:
        draw_height = PIX_RES_Y - draw_y
    if draw_height > 0:
        display.vline(enemy_projectile_x, draw_y, draw_height, 1)


def _spawn_explosion(x, y):
    global explosions
    now = ticks_ms()
    explosion = {
        "x": clamp(x, 0, PIX_RES_X - BLAST_WIDTH),
        "y": clamp(y, 0, PIX_RES_Y - BLAST_HEIGHT),
        "expires": ticks_add(now, EXPLOSION_DURATION_MS),
    }
    explosions.append(explosion)


def _update_explosions(now_ms):
    global explosions
    explosions = [exp for exp in explosions if ticks_diff(exp["expires"], now_ms) > 0]


def _draw_explosions():
    for exp in explosions:
        display.blit(FB_BLAST, exp["x"], exp["y"])


def _draw_scene(now_ms):
    display.fill(0)
    display.text("SCORE {}".format(score), 0, 0, 1)
    _draw_hearts(now_ms)
    for enemy in _iter_enemies():
        if enemy["alive"]:
            display.blit(enemy["fb"], enemy["x"], enemy["y"])
    if ship_visible:
        display.blit(FB_SHIP, ship_x, SHIP_Y)
    _draw_projectile()
    _draw_enemy_projectile()
    _draw_explosions()
    display.show()


def _draw_game_over():
    display.fill(0)
    title = "GAME OVER"
    score_text = "Score {}".format(score)
    prompt = "Press to restart"
    title_x = max(0, (PIX_RES_X - len(title) * 8) // 2)
    score_x = max(0, (PIX_RES_X - len(score_text) * 8) // 2)
    prompt_x = max(0, (PIX_RES_X - len(prompt) * 8) // 2)
    display.text(title, title_x, 20, 1)
    display.text(score_text, score_x, 32, 1)
    display.text(prompt, prompt_x, 46, 1)
    display.show()


def _draw_victory():
    display.fill(0)
    title = "YOU WIN!"
    prompt = "Press to restart"
    title_x = max(0, (PIX_RES_X - len(title) * 8) // 2)
    prompt_x = max(0, (PIX_RES_X - len(prompt) * 8) // 2)
    display.text(title, title_x, 20, 1)
    display.text(prompt, prompt_x, 46, 1)
    display.show()

def _update_ship_position():
    global last_reported_position, ship_x
    current_position = encoder.value()
    if last_reported_position == current_position:
        return
    delta = current_position - last_reported_position
    last_reported_position = current_position
    if delta != 0:
        ship_x = clamp(ship_x + delta * SHIP_STEP_PIXELS, SHIP_MIN_X, SHIP_MAX_X)


def _handle_fire_button(now_ms, paused):
    global last_button_state, last_button_time
    button_state = encoder_sw.value()
    if button_state == last_button_state:
        return
    if ticks_diff(now_ms, last_button_time) < BUTTON_DEBOUNCE_MS:
        return
    last_button_state = button_state
    last_button_time = now_ms
    if button_state == 0:
        if game_over or victory:
            _reset_game()
        elif not paused:
            _fire_projectile()


def _reset_enemy_projectile():
    global enemy_projectile_active, enemy_projectile_x, enemy_projectile_y
    enemy_projectile_active = False
    enemy_projectile_x = 0
    enemy_projectile_y = 0


def _spawn_enemy_projectile(enemy):
    global enemy_projectile_active, enemy_projectile_x, enemy_projectile_y
    enemy_projectile_active = True
    enemy_projectile_x = enemy["x"] + enemy["width"] // 2
    enemy_projectile_y = enemy["y"] + enemy["height"]


def _maybe_fire_enemy(now_ms):
    global last_enemy_fire_ms
    if ticks_diff(now_ms, last_enemy_fire_ms) < ENEMY_FIRE_INTERVAL_MS:
        return
    last_enemy_fire_ms = now_ms
    available = _alive_enemies()
    if not available:
        return
    choice = available[getrandbits(16) % len(available)]
    _spawn_enemy_projectile(choice)


def _check_victory():
    global victory
    if victory or game_over:
        return
    if not _alive_enemies():
        victory = True
        _reset_enemy_projectile()


def _handle_player_hit(now_ms):
    global ship_visible, pause_until_ms, last_enemy_fire_ms, lives
    global pending_life_loss, pending_loss_start_ms
    ship_visible = False
    pause_until_ms = ticks_add(now_ms, PLAYER_HIT_PAUSE_MS)
    last_enemy_fire_ms = now_ms
    _reset_enemy_projectile()
    if not pending_life_loss:
        pending_life_loss = lives > 0
        pending_loss_start_ms = now_ms
    blast_x = ship_x + (SHIP_WIDTH - BLAST_WIDTH) // 2
    blast_y = SHIP_Y + (SHIP_HEIGHT - BLAST_HEIGHT) // 2
    _spawn_explosion(blast_x, blast_y)


def _check_player_hit(now_ms):
    if not enemy_projectile_active or not ship_visible:
        return
    if _rects_overlap(
        enemy_projectile_x,
        enemy_projectile_y,
        ENEMY_PROJECTILE_WIDTH,
        ENEMY_PROJECTILE_HEIGHT,
        ship_x,
        SHIP_Y,
        SHIP_WIDTH,
        SHIP_HEIGHT,
    ):
        _handle_player_hit(now_ms)


def _update_enemy_projectile(now_ms):
    global enemy_projectile_y
    if not enemy_projectile_active:
        return
    enemy_projectile_y += ENEMY_PROJECTILE_SPEED
    if enemy_projectile_y >= PIX_RES_Y:
        _reset_enemy_projectile()
        return
    _check_player_hit(now_ms)


def _finalize_life_loss():
    global pending_life_loss, lives
    if pending_life_loss:
        pending_life_loss = False
        if lives > 0:
            lives -= 1


def _reset_game():
    global ship_x, score, ship_visible, pause_until_ms, lives, game_over, victory
    global last_enemy_fire_ms, enemy_rows, last_reported_position
    global explosions, pending_life_loss, pending_loss_start_ms
    ship_x = (PIX_RES_X - SHIP_WIDTH) // 2
    score = 0
    ship_visible = True
    pause_until_ms = None
    lives = MAX_LIVES
    game_over = False
    victory = False
    _reset_projectile()
    _reset_enemy_projectile()
    enemy_rows = _build_enemy_rows()
    last_enemy_fire_ms = ticks_ms()
    last_reported_position = encoder.value()
    explosions = []
    pending_life_loss = False
    pending_loss_start_ms = 0

while True:
    now = ticks_ms()
    _update_explosions(now)

    paused = False
    if pause_until_ms is not None:
        if ticks_diff(pause_until_ms, now) > 0:
            paused = True
        else:
            pause_until_ms = None
            _finalize_life_loss()
            if lives == 0:
                game_over = True
                ship_visible = False
            else:
                ship_visible = True
                last_enemy_fire_ms = now

    _handle_fire_button(now, paused)

    if not paused and not game_over and not victory:
        _update_ship_position()
        _update_projectile()
        _update_enemy_projectile(now)
        _update_enemy_rows(now)
        _apply_projectile_hits()
        _maybe_fire_enemy(now)

    if game_over:
        _draw_game_over()
    elif victory:
        _draw_victory()
    else:
        _draw_scene(now)

    sleep_ms(16)
