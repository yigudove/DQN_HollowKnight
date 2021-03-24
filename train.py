# -*- coding: utf-8 -*-
import numpy as np
from tensorflow.keras.models import load_model
import os
import cv2
import time

from Model import Model
from DQN import DQN
from Agent import Agent
from ReplayMemory import ReplayMemory


import Tool.Helper
from Tool.Actions import take_action, restart
from Tool.GrabScreen import grab_screen
from Tool.GetHP import boss_hp, player_hp

window_size = (0,0,1920,1017)
station_size = (230, 230, 1670, 930)

HP_WIDTH = 768
HP_HEIGHT = 407
WIDTH = 200
HEIGHT = 100
ACTION_DIM = 13
INPUT_SHAPE = (HEIGHT, WIDTH, 3)

LEARN_FREQ = 30  # 训练频率，不需要每一个step都learn，攒一些新增经验后再learn，提高效率
MEMORY_SIZE = 1500  # replay memory的大小，越大越占用内存
MEMORY_WARMUP_SIZE = 150  # replay_memory 里需要预存一些经验数据，再从里面sample一个batch的经验让agent去learn
BATCH_SIZE = 16  # 每次给agent learn的数据数量，从replay memory随机里sample一批数据出来
LEARNING_RATE = 0.001  # 学习率
GAMMA = 0.99  # reward 的衰减因子，一般取 0.9 到 0.999 不等

action_name = ["Nothing", "Move_Left", "Move_Right", "Attack_Left", "Attack_Right", "Attack_Up",
           "Short_Jump", "Mid_Jump", "Long_Jump", "Skill_Down", "Skill_Left", 
           "Skill_Right", "Skill_Up", "Rush_Left", "Rush_Right", "Cure"]



def run_episode(algorithm,agent,rpm,PASS_COUNT,paused):
    restart()
    
    station = cv2.resize(cv2.cvtColor(grab_screen(station_size), cv2.COLOR_RGBA2BGR),(WIDTH,HEIGHT))
    hp_station = cv2.cvtColor(cv2.resize(grab_screen(window_size),(HP_WIDTH,HP_HEIGHT)),cv2.COLOR_BGR2GRAY)

    boss_blood = boss_hp(hp_station, 570)
    last_hp = boss_blood
    self_blood = player_hp(hp_station)
    min_hp = 9

    step = 0
    done = 0
    total_reward = 0

    last_time = time.time()

    while True:
        last_time = time.time()
        step += 1
        action = agent.sample(station)

        take_action(action)
        
        next_station = cv2.resize(cv2.cvtColor(grab_screen(station_size), cv2.COLOR_RGBA2BGR),(WIDTH,HEIGHT))
        next_hp_station = cv2.cvtColor(cv2.resize(grab_screen(window_size),(HP_WIDTH,HP_HEIGHT)),cv2.COLOR_BGR2GRAY)

        next_boss_blood = boss_hp(next_hp_station, last_hp)
        last_hp = boss_blood
        next_self_blood = player_hp(next_hp_station)

        reward, done, min_hp = Tool.Helper.action_judge(action, boss_blood, next_boss_blood,
                                                               self_blood, next_self_blood, min_hp)
        print(action_name[action], ": ", reward)
        rpm.append((station,action,reward,next_station,done))
        if (len(rpm) > MEMORY_WARMUP_SIZE) and (step % LEARN_FREQ == 0):
            batch_station,batch_action,batch_reward,batch_next_station,batch_done = rpm.sample(BATCH_SIZE)
            algorithm.learn(batch_station,batch_action,batch_reward,batch_next_station,batch_done)
            
        station = next_station
        self_blood = next_self_blood
        boss_blood = next_boss_blood

        total_reward += reward
        paused = Tool.Helper.pause_game(paused)
        if done == 1:
            break
        elif done == 2:
            PASS_COUNT += 1
            time.sleep(6)
            break
    return total_reward, step


if __name__ == '__main__':

    os.environ['CUDA_VISIBLE_DEVICES'] = '/gpu:0'
    PASS_COUNT = 0
    rpm = ReplayMemory(MEMORY_SIZE)         # DQN的经验回放池


    model = Model(INPUT_SHAPE, ACTION_DIM)
    if os.path.exists('dqn_model.h5'):
        print("model exists , load model\n")
        model.model = load_model('dqn_model.h5')
    algorithm = DQN(model, gamma=GAMMA, learnging_rate=LEARNING_RATE)
    agent = Agent(ACTION_DIM,algorithm,e_greed=0.5,e_greed_decrement=1e-5)
    
    paused = True
    paused = Tool.Helper.pause_game(paused)

    # 先往经验池里存一些数据，避免最开始训练的时候样本丰富度不够
    while len(rpm) < MEMORY_WARMUP_SIZE:
        print("WARM UP:", len(rpm))
        run_episode(algorithm, agent, rpm, PASS_COUNT, paused)

    max_episode = 3000

    # 开始训练
    episode = 0
    while episode < max_episode:    # 训练max_episode个回合，test部分不计算入episode数量
        # 训练
        total_reward, total_step = run_episode(algorithm,agent,rpm, PASS_COUNT, paused)
        episode += 1
        print("Episode: ", episode, ", mean(reward):", total_reward/total_step)
        # 保存模型
        if episode % 10 == 9:
            save_path = './dqn_model.h5'
            model.model.save(save_path)
