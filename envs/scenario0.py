import gym
from gym.spaces import Box, Discrete
from gym.utils import seeding
import numpy as np

from .world import World
from .agents import Car, Building, Pedestrian, Painting
from .geometry import Point
import time

class Scenario0(gym.Env):
	def __init__(self):
		self.seed(0) # just in case we forget seeding
		
		self.init_ego = Car(Point(20, 20), heading = np.pi/2)
		self.init_ego.velocity = Point(1., 0.)
		self.init_adv = Car(Point(105, 90), heading = np.pi, color='blue')
		self.init_adv.velocity = Point(0., 0.)
		
		self.collision_point = Point(20, 90)
		self.target = Point(20, 120)
		self.wall = Point(25, 80)
		
		self.noise_adv_pos = 1.0
		self.noise_adv_vel = 1.0
		self.dt = 0.1
		self.T = 200
		self.reward = 0
		self.initiate_world()
		self.reset()
		
	def initiate_world(self):
		self.world = World(self.dt, width = 120, height = 120, ppm = 5)
		self.world.add(Building(Point(72.5, 107.5), Point(95, 25)))
		self.world.add(Building(Point(7.5, 107.5), Point(15, 25)))
		self.world.add(Building(Point(7.5, 40), Point(15, 80)))
		self.world.add(Building(Point(72.5, 40), Point(95, 80)))

		
	def reset(self):
		self.ego = self.init_ego.copy()
		self.ego.min_speed = 0.
		self.ego.max_speed = 20.
		self.adv = self.init_adv.copy()
		self.adv.min_speed = 3.
		self.adv.max_speed = 12.
		self.ego_reaction_time = 0.6
		self.ego_saw_adv = False
		self.add_noise()
		self.reward = 0

		self.world.reset()
		self.initiate_world()
		self.world.add(self.ego)
		self.world.add(self.adv)
		
		return self._get_obs()
		
	def close(self):
			self.world.close()
		
	def add_noise(self):
		self.ego.center += Point(0, 20*self.np_random.rand() - 10)
		self.adv.center += Point(20*self.np_random.rand() - 10, 0)
		self.ego_reaction_time += self.np_random.rand() - 0.5

	@property
	def observation_space(self):
		low = np.array([0, 0, -600 - self.noise_adv_pos/2., self.adv.min_speed - self.noise_adv_vel/2.])
		high= np.array([self.target.y + self.ego.max_speed*self.dt, self.ego.max_speed, 80, self.adv.max_speed + self.noise_adv_vel/2.])
		return Box(low=low, high=high)

	@property
	def action_space(self):
		return Box(low=np.array([-3.5]), high=np.array([2.]))
	
	def seed(self, seed):
		self.np_random, seed = seeding.np_random(seed)
		return [seed]
	
	@property
	def ego_can_see_adv(self):
		if self.ego_saw_adv or self.ego.y >= self.wall.y:
			return True
		furthest_point_seen = self.wall.x + self.wall.x*(self.collision_point.y - self.wall.y) / (self.wall.y - (self.ego.y - self.ego_reaction_time * self.ego.yp))
		self.ego_saw_adv = furthest_point_seen > self.adv.x
		return self.ego_saw_adv
		
	def get_adv_control(self):
		if np.abs(self.adv.xp) > self.adv.max_speed:
			return np.array([0, -2.], dtype=np.float32)
		elif np.abs(self.adv.xp) < self.adv.min_speed:
			return np.array([0, 2.], dtype=np.float32)
		else:
			ttc_ego = (self.collision_point.y - self.ego.y) / np.abs(self.ego.yp + 1e-8)
			ttc_adv = (self.adv.x - self.collision_point.x) / np.abs(self.adv.xp + 1e-8)
			if ttc_adv < ttc_ego:
				return np.array([0, -2.], dtype=np.float32)
			else:
				return np.array([0, 2.], dtype=np.float32)
		
	def get_ego_control(self,policy_no=0):
		ttc_ego = (self.collision_point.y - self.ego.y) / np.abs(self.ego.yp + 1e-8)
		ttc_adv = (self.adv.x - self.collision_point.x) / np.abs(self.adv.xp + 1e-8)
		if policy_no==0: # aggressive
			if ttc_ego < 0.05 or ttc_adv < 0:
				return np.array([0, 1.95 + 0.05*self.np_random.rand()], dtype=np.float32)
			elif ttc_ego < ttc_adv - 0.1 or not self.ego_can_see_adv:
				return np.array([0, np.minimum(2.0, np.maximum(1.2, self.ego.inputAcceleration + self.np_random.rand()*0.2 - 0.1))], dtype=np.float32)
			else:
				return np.array([0, -3.25-np.random.rand()*0.25], dtype=np.float32)
			
		elif policy_no==1: # cautious
			ttw_ego = (self.wall.y - self.ego.y)/np.abs(self.ego.yp + 1e-8)
			if ttc_ego < 0.05 or ttc_adv < 0:
				return np.array([0, 1.95 + 0.05*self.np_random.rand()], dtype=np.float32)
			elif ttw_ego > 1.0 and ttw_ego < 4.5:
				return np.array([0, 0], dtype=np.float32)
			elif ttc_ego < ttc_adv - 0.3 or not self.ego_can_see_adv:
				return np.array([0, np.minimum(1.0, np.maximum(0.4, self.ego.inputAcceleration + self.np_random.rand()*0.2 - 0.1))], dtype=np.float32)
			else:
				return np.array([0, -2.75-np.random.rand()*0.25], dtype=np.float32)

		elif policy_no == 2:  # normal
			ttw_ego = (self.wall.y - self.ego.y) / np.abs(self.ego.yp + 1e-8)
			if ttc_ego < 0.05 or ttc_adv < 0:
				return np.array([0, 1.95 + 0.05 * self.np_random.rand()], dtype=np.float32)
			elif ttw_ego > 1.0 and ttw_ego < 3:
				return np.array([0, 0], dtype=np.float32)
			elif ttc_ego < ttc_adv - 0.2 or not self.ego_can_see_adv:
				return np.array([0, np.minimum(1.5, np.maximum(1, self.ego.inputAcceleration + self.np_random.rand() * 0.2 - 0.1))],dtype=np.float32)
			else:
				return np.array([0, -3 - np.random.rand() * 0.25], dtype=np.float32)

	@property
	def target_reached(self):
		return self.ego.y >= self.target.y
	
	@property
	def collision_exists(self):
		return self.ego.collidesWith(self.adv)
		
	def step(self, action):
		while type(action) == list:
			action = action[0]
		action = np.clip(action, self.action_space.low, self.action_space.high)
		
		ego_action = np.array([0, action], dtype=np.float32)
		adv_action = self.get_adv_control()
		# print("ego action: ", ego_action)
		self.ego.set_control(*ego_action)
		self.adv.set_control(*adv_action)
		
		self.world.tick()

		self.reward = 100 * (self.ego.y - self.target.y)
		# self.reward +=
		if self.collision_exists:
			self.reward -= 100000
		# print(self.world.t)
		self.reward -= 10 * self.world.t
		return self._get_obs(), self.reward, self.collision_exists or self.target_reached or self.world.t >= self.T, self.world.t
		
	def _get_obs(self):
		if self.ego_can_see_adv:
			return np.array([self.ego.center.y, self.ego.velocity.y, self.adv.center.x + self.noise_adv_pos*self.np_random.rand() - self.noise_adv_pos/2., self.adv.velocity.x + self.noise_adv_vel*self.np_random.rand() - self.noise_adv_vel/2.])
		return np.array([self.ego.center.y, self.ego.velocity.y, 0., 0.])
		

	def render(self, mode='rgb'):
		self.world.render()




