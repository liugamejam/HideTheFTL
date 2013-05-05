#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This is sample of how you can implement a tile-based game, not unlike
the RPG games known from consoles, in pygame. It's not a playable game,
but it can be turned into one. Care has been taken to comment it clearly,
so that you can use it easily as a starting point for your game.

The program reads a level definition from a "level.map" file, and uses the
graphics referenced for that file to display a tiled map on the screen and
let you move an animated player character around it.

Note that a lot of additional work is needed to turn it into an actual game.

@copyright: 2008, 2009 Radomir Dopieralski <qq@sheep.art.pl>
@license: BSD, see COPYING for details

"""

import ConfigParser
import copy
import random

import pygame
import pygame.locals as pg

# Motion offsets for particular directions
#     N  E  S   W
DX = [0, 1, 0, -1]
DY = [-1, 0, 1, 0]

# Dimensions of the map tiles
MAP_TILE_WIDTH, MAP_TILE_HEIGHT = 24, 16

class TileCache(object):
	"""Load the tilesets lazily into global cache"""

	def __init__(self,  width=32, height=None):
		self.width = width
		self.height = height or width
		self.cache = {}

	def __getitem__(self, filename):
		"""Return a table of tiles, load it from disk if needed."""

		key = (filename, self.width, self.height)
		try:
			return self.cache[key]
		except KeyError:
			tile_table = self._load_tile_table(filename, self.width,
											   self.height)
			self.cache[key] = tile_table
			return tile_table

	def _load_tile_table(self, filename, width, height):
		"""Load an image and split it into tiles."""

		image = pygame.image.load(filename).convert()
		image_width, image_height = image.get_size()
		tile_table = []
		for tile_x in range(0, image_width/width):
			line = []
			tile_table.append(line)
			for tile_y in range(0, image_height/height):
				rect = (tile_x*width, tile_y*height, width, height)
				line.append(image.subsurface(rect))
		return tile_table


class SortedUpdates(pygame.sprite.RenderUpdates):
	"""A sprite group that sorts them by depth."""

	def sprites(self):
		"""The list of sprites in the group, sorted by depth."""

		return sorted(self.spritedict.keys(), key=lambda sprite: sprite.depth)


class Shadow(pygame.sprite.Sprite):
	"""Sprite for shadows."""

	def __init__(self, owner):
		pygame.sprite.Sprite.__init__(self)
		self.image = SPRITE_CACHE["images/shadow.png"][0][0]
		self.image.set_alpha(64)
		self.rect = self.image.get_rect()
		self.owner = owner

	def update(self, *args):
		"""Make the shadow follow its owner."""

		self.rect.midbottom = self.owner.rect.midbottom


class Sprite(pygame.sprite.Sprite):
	"""Sprite for animated items and base class for Player."""

	is_player = False

	def __init__(self, pos=(0, 0), frames=None):
		super(Sprite, self).__init__()
		if frames:
			self.frames = frames
		self.image = self.frames[0][0]
		self.rect = self.image.get_rect()
		self.animation = self.stand_animation()
		self.pos = pos

	def _get_pos(self):
		"""Check the current position of the sprite on the map."""

		return (self.rect.midbottom[0]-12)/24, (self.rect.midbottom[1]-16)/16

	def _set_pos(self, pos):
		"""Set the position and depth of the sprite on the map."""

		self.rect.midbottom = pos[0]*24+12, pos[1]*16+16
		self.depth = self.rect.midbottom[1]

	pos = property(_get_pos, _set_pos)

	def move(self, dx, dy):
		"""Change the position of the sprite on screen."""

		self.rect.move_ip(dx, dy)
		self.depth = self.rect.midbottom[1]

	def stand_animation(self):
		"""The default animation."""

		while True:
			# Change to next frame every two ticks
			for frame in self.frames[0]:
				self.image = frame
				yield None
				yield None

	def update(self, *args):
		"""Run the current animation."""
		self.animation.next()


class Body(Sprite):
	""" Display and animate the body. """

	is_player = False
	carried = False
	bloody = True

	def __init__(self, pos=(2,2)):
		self.frames = SPRITE_CACHE["images/skeleton.png"]
		Sprite.__init__(self, pos)
		self.direction = 2
		
		
class NPC(Sprite):
	is_player = False
	def __init__(self, pos=(2,2)):
		self.frames = SPRITE_CACHE["images/npc.png"]
		Sprite.__init__(self, pos)
		self.direction = 2
		
	def stand_animation(self):
		"""The default animation."""

		while True:
			# Change to next frame every two ticks
			for frame in self.frames[2]:
				self.image = frame
				yield None
				yield None
		

class Player(Sprite):
	""" Display and animate the player character."""

	is_player = True
	carrying = False

	def __init__(self, pos=(1, 1)):
		self.frames = SPRITE_CACHE["images/player.png"]
		Sprite.__init__(self, pos)
		self.direction = 2
		self.animation = None
		self.image = self.frames[self.direction][0]

	def walk_animation(self):
		"""Animation for the player walking."""

		# This animation is hardcoded for 4 frames and 16x24 map tiles
		for frame in range(4):
			self.image = self.frames[self.direction][frame]
			yield None
			self.move(3*DX[self.direction], 2*DY[self.direction])
			yield None
			self.move(3*DX[self.direction], 2*DY[self.direction])

	def update(self, *args):
		"""Run the current animation or just stand there if no animation set."""

		if self.animation is None:
			self.image = self.frames[self.direction][0]
		else:
			try:
				self.animation.next()
			except StopIteration:
				self.animation = None

class Square(object):
	def __init__(self, x, y, props):
		self.x = x
		self.y = y
		self.properties = props
		self.propertytosprite = {}

	def get_bool(self,prop):
		value = self.properties.get(prop)
		return value in (True, 1, 'true', 'yes', 'True', 'Yes', '1', 'on', 'On')

	def set_bool(self,prop):
		self.properties[prop] = True

	def unset_bool(self,prop):
		self.properties[prop] = False

	def switch_bool(self,prop):
		currval = get_bool(self,prop)
		self.properties[prop] = not currval

	def set_bool_with_sprite(self,prop,sprite):
		self.propertytosprite[prop] = sprite
		self.set_bool(prop)

	def unset_bool_with_sprite(self,prop):
		retval = self.propertytosprite[prop]
		del self.propertytosprite[prop]
		self.unset_bool(prop)
		return retval

class Squares(object):
	def __init__(self, lvl):
		self.squares = []
		self.width = lvl.width
		self.height = lvl.height
		for i in range(0, self.width):
			templist = []
			for j in range(0, self.height):
				tempsquare = Square(i, j, lvl.get_tile(i,j))
				templist.append(copy.deepcopy(tempsquare))
			self.squares.append(copy.copy(templist))

	def get_bool(self,x,y,prop):
		return self.squares[x][y].get_bool(prop)

	def set_bool(self,x,y,prop):
		self.squares[x][y].set_bool(prop)

	def unset_bool(self,x,y,prop):
		self.squares[x][y].unset_bool(prop)

	def swtich_bool(self,x,y,prop):
		self.squares[x][y].switch_bool(prop)

	def count_property(self,prop):
		cnt = 0
		for x in range(0,self.width):
			for y in range(0,self.height):
				if self.get_bool(x,y,prop):
					cnt = cnt + 1
		return cnt

	def set_bool_with_sprite(self,x,y,prop,sprite):
		self.squares[x][y].set_bool_with_sprite(prop,sprite)

	def unset_bool_with_sprite(self,prop):
		return self.squres[x][y].unset_bool_with_sprite(prop,sprite)


class Level(object):
	"""Load and store the map of the level, together with all the items."""

	def __init__(self, filename="level.map"):
		self.tileset = ''
		self.map = []
		self.items = {}
		self.key = {}
		self.width = 0
		self.height = 0
		self.load_file(filename)

	def load_file(self, filename="level.map"):
		"""Load the level from specified file."""

		parser = ConfigParser.ConfigParser()
		parser.read(filename)
		self.tileset = parser.get("level", "tileset")
		self.map = parser.get("level", "map").split("\n")
		for section in parser.sections():
			if len(section) == 1:
				desc = dict(parser.items(section))
				self.key[section] = desc
		self.width = len(self.map[0])
		self.height = len(self.map)
		for y, line in enumerate(self.map):
			for x, c in enumerate(line):
				if not self.is_wall(x, y) and 'sprite' in self.key[c]:
					self.items[(x, y)] = self.key[c]

	def render(self):
		"""Draw the level on the surface."""

		wall = self.is_wall
		tiles = MAP_CACHE[self.tileset]
		image = pygame.Surface((self.width*MAP_TILE_WIDTH, self.height*MAP_TILE_HEIGHT))
		overlays = {}
		for map_y, line in enumerate(self.map):
			for map_x, c in enumerate(line):
				if wall(map_x, map_y):
					# Draw different tiles depending on neighbourhood
					if not wall(map_x, map_y+1):
						if wall(map_x+1, map_y) and wall(map_x-1, map_y):
							tile = 1, 2
						elif wall(map_x+1, map_y):
							tile = 0, 2
						elif wall(map_x-1, map_y):
							tile = 2, 2
						else:
							tile = 3, 2
					else:
						if wall(map_x+1, map_y+1) and wall(map_x-1, map_y+1):
							tile = 1, 1
						elif wall(map_x+1, map_y+1):
							tile = 0, 1
						elif wall(map_x-1, map_y+1):
							tile = 2, 1
						else:
							tile = 3, 1
					# Add overlays if the wall may be obscuring something
					if not wall(map_x, map_y-1):
						if wall(map_x+1, map_y) and wall(map_x-1, map_y):
							over = 1, 0
						elif wall(map_x+1, map_y):
							over = 0, 0
						elif wall(map_x-1, map_y):
							over = 2, 0
						else:
							over = 3, 0
						overlays[(map_x, map_y)] = tiles[over[0]][over[1]]
				else:
					try:
						tile = self.key[c]['tile'].split(',')
						tile = int(tile[0]), int(tile[1])
					except (ValueError, KeyError):
						# Default to ground tile
						tile = 0, 3
				tile_image = tiles[tile[0]][tile[1]]
				image.blit(tile_image,
						   (map_x*MAP_TILE_WIDTH, map_y*MAP_TILE_HEIGHT))
		return image, overlays

	def get_tile(self, x, y):
		"""Tell what's at the specified position of the map."""

		try:
			return self.items[(x,y)]
		except KeyError:
			try:
				char = self.map[y][x]
				return self.key[char]
			except IndexError:
				return {}

	def get_bool(self, x, y, name):
		"""Tell if the specified flag is set for position on the map."""

		value = self.get_tile(x, y).get(name)
		return value in (True, 1, 'true', 'yes', 'True', 'Yes', '1', 'on', 'On')

	def set_bool(self, x, y, name):
		value = self.get_tile(x,y)
		value[name] = True

	def unset_bool(self, x, y, name):
		value = self.get_tile(x,y)
		value[name] = False

	def is_wall(self, x, y):
		"""Is there a wall?"""
		return self.get_bool(x, y, 'wall')

	def is_blocking(self, x, y):
		"""Is this place blocking movement?"""

		if not 0 <= x < self.width or not 0 <= y < self.height:
			return True
		return self.get_bool(x, y, 'block')
		
	def is_stairs(self, x, y, type):
		"""Is there a Staicase on this tile?"""
		
		return self.get_bool(x, y, type)


class Game(object):
	"""The main game object."""

	def __init__(self):
		self.screen = pygame.display.get_surface()
		self.npc_list = []
		self.pressed_key = None
		self.game_over = False
		self.shadows = pygame.sprite.RenderUpdates()
		self.sprites = SortedUpdates()
		self.overlays = pygame.sprite.RenderUpdates()
		self.use_level(Level())
		self.squares = Squares(self.level)

	def use_level(self, level):
		"""Set the level as the current one."""

		self.shadows = pygame.sprite.RenderUpdates()
		self.sprites = SortedUpdates()
		self.overlays = pygame.sprite.RenderUpdates()
		self.level = level
		# Populate the game with the level's objects
		for pos, tile in level.items.iteritems():
			if tile.get("player") in ('true', '1', 'yes', 'on'):
				sprite = Player(pos)
				self.player = sprite
			elif tile.get("body") in ('true', '1', 'yes', 'on'):
				sprite = Body(pos)
				self.body = sprite 
			elif tile.get("npc") in ('true', '1', 'yes', 'on'):
				sprite = NPC(pos)
				self.npc_list.append(sprite)
			else:
				sprite = Sprite(pos, SPRITE_CACHE[tile["sprite"]])
			self.sprites.add(sprite)
			self.shadows.add(Shadow(sprite))
		# Render the level map
		self.background, overlays = self.level.render()
		# Add the overlays for the level map
		for (x, y), image in overlays.iteritems():
			overlay = pygame.sprite.Sprite(self.overlays)
			overlay.image = image
			overlay.rect = image.get_rect().move(x*24, y*16-16)

	def control(self):
		"""Handle the controls of the game."""

		keys = pygame.key.get_pressed()

		def pressed(key):
			"""Check if the specified key is pressed."""

			return self.pressed_key == key or keys[key]

		def walk(d):
			"""Start walking in specified direction."""

			x, y = self.player.pos
			self.player.direction = d
			if not self.level.is_blocking(x+DX[d], y+DY[d]):
				self.player.animation = self.player.walk_animation()
				
		def gostairs(floor):
			""" Stat walking in the stairs. """
			# For now it only exits the game

			# If carring the body to a new floor mission sucessfull
			x,y = self.player.pos
			if self.level.is_stairs(x, y, 'stairs'):
				if self.level.is_stairs(x, y, floor):
					if self.player.carrying:
						print('Congratulation! You managed to hide the body...')
						self.game_over = True
					else:
						print('DEBUG: Not carrying the body')
				else:
					print('DEBUG: Stairs goes in other direction!')
			else:
				print('DEBUG: You can`t find any stairs.')

		def pickdrop():
			x,y = self.player.pos
			if self.player.carrying:
				self.body.pos = x,y
				self.body.carried = False
				self.player.carrying = False
			else:
				x2,y2 = self.body.pos
				if x == x2 and y == y2:
					self.body.carried = True
					self.player.carrying = True

		def checkbody():
			if self.body.carried:
				if(self.body.bloody):
					x,y = self.body.pos
					if random.randint(1, 100) < 60:
						if not self.squares.get_bool(x,y,'blood'):
							sprite = Sprite(self.body.pos,SPRITE_CACHE["images/blood.png"])
							print("Adding blood at: " + str(x) + ", " + str(y) + ". Total of " + str(self.squares.count_property('blood')) + " squares have blood.")		
							self.squares.set_bool_with_sprite(x,y,'blood',sprite)
							self.sprites.add(sprite)
				self.body.pos = self.player.pos
		
		def rest():
			x,y = self.player.pos
			if self.level.get_bool(x, y, 'bed'): 
				print( 'DEBUG: Time to sleep' )
			else:
				print( 'DEBUG: Can`t sleep on the floor! Find a Bed.' )

		if pressed(pg.K_UP):
			walk(0)
			checkbody()
		elif pressed(pg.K_DOWN):
			walk(2)
			checkbody()
		elif pressed(pg.K_LEFT):
			walk(3)
			checkbody()
		elif pressed(pg.K_RIGHT):
			walk(1)
			checkbody()
		elif pressed(pg.K_SPACE):
			pickdrop()
		elif( pressed(pg.K_d) ):
			gostairs('down')
		elif( pressed(pg.K_u) ):
			gostairs('up')
		elif( pressed(pg.K_s) ):
			rest()
		# elif ( pressed(pg.K_GREATER) or ( pressed(pg.K_GREATER) and get_mods(pg.KMOD_SHIFT) ) ):
			# gostairs("down")
		# elif ( pressed(pg.K_LESS) or ( pressed(pg.K_LESS) and get_mods(pg.KMOD_SHIFT) ) ):
			# gostairs("up")
		self.pressed_key = None

	def main(self):
		"""Run the main loop."""

		clock = pygame.time.Clock()
		# Draw the whole screen initially
		self.screen.blit(self.background, (0, 0))
		self.overlays.draw(self.screen)
		pygame.display.flip()
		# The main game loop
		while not self.game_over:
			# Don't clear shadows and overlays, only sprites.
			self.sprites.clear(self.screen, self.background)
			self.sprites.update()
			# If the player's animation is finished, check for keypresses
			if self.player.animation is None:
				self.control()
				self.player.update()
			self.shadows.update()
			# Don't add shadows to dirty rectangles, as they already fit inside
			# sprite rectangles.
			self.shadows.draw(self.screen)
			dirty = self.sprites.draw(self.screen)
			# Don't add ovelays to dirty rectangles, only the places where
			# sprites are need to be updated, and those are already dirty.
			self.overlays.draw(self.screen)
			# Update the dirty areas of the screen
			pygame.display.update(dirty)
			# Wait for one tick of the game clock
			clock.tick(50)
			# Process pygame events
			for event in pygame.event.get():
				if event.type == pg.QUIT:
					self.game_over = True
				elif event.type == pg.KEYDOWN:
					self.pressed_key = event.key


if __name__ == "__main__":
	SPRITE_CACHE = TileCache()
	MAP_CACHE = TileCache(MAP_TILE_WIDTH, MAP_TILE_HEIGHT)
	TILE_CACHE = TileCache(128,128)
	pygame.init()
	pygame.display.set_mode((1024,768))
	Game().main()
