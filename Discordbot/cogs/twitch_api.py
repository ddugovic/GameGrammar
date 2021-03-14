import discord
import json
import requests
from datetime import datetime, timedelta
from discord.ext import commands, tasks

import config
import bot_tools
import bot_db


def create_notif_embed(title, image_url, game, viewers):
    embed = discord.Embed(
        title="GameGrammar is live", colour=discord.Colour.blue(), url="https://twitch.tv/gamegrammar",
        description=title
    )
    embed.set_image(url=image_url)
    embed.set_thumbnail(
        url="https://static-cdn.jtvnw.net/jtv_user_pictures/6f4fd276-f717-41a7-986d-35f22cd68c38-profile_image-300x300.png"
    )

    embed.add_field(name="Game", value=game, inline=True)
    embed.add_field(name="Viewers", value=viewers, inline=True)
    return embed


def create_offline_embed(user, latest_title, latest_game, follow_count, sub_count, view_count, latest_vid_title, latest_vid_url):
    embed = discord.Embed(
        title="GameGrammar Twitch Stats", 
        colour=discord.Colour.blue(), 
        url="https://twitch.tv/gamegrammar", 
        description="The stats for the GameGrammar Twitch channel!"
    )

    embed.set_thumbnail(url="https://static-cdn.jtvnw.net/jtv_user_pictures/6f4fd276-f717-41a7-986d-35f22cd68c38-profile_image-300x300.png")
    embed.set_footer(text=f"Requested by {user.name}")

    embed.add_field(
        name="Status", 
        value="**Offline**", 
        inline=False
    )
    embed.add_field(
        name="Latest Title", 
        value=latest_title, 
        inline=True
    )
    embed.add_field(
        name="Latest Game", 
        value=latest_game, 
        inline=True
    )
    embed.add_field(
        name="Total views", 
        value=view_count, 
        inline=False
    )
    embed.add_field(
        name="Followers", 
        value=follow_count, 
        inline=False
    )
    embed.add_field(
        name="Subscribers", 
        value=sub_count-1, 
        inline=False
    )
    embed.add_field(
        name="Latest video", 
        value=f"{latest_vid_title}\n{latest_vid_url}", 
        inline=False
    )

    return embed


def create_live_embed(user, title, game, live_views, follow_count, sub_count, view_count, thumb_url):
    embed = discord.Embed(
        title="GameGrammar Twitch Stats", 
        colour=discord.Colour.blue(), 
        url="https://twitch.tv/gamegrammar", 
        description="The stats for the GameGrammar Twitch channel!"
    )

    embed.set_image(url=thumb_url)
    embed.set_thumbnail(url="https://static-cdn.jtvnw.net/jtv_user_pictures/6f4fd276-f717-41a7-986d-35f22cd68c38-profile_image-300x300.png")
    embed.set_footer(text=f"Requested by {user.name}")

    embed.add_field(
        name="Status", 
        value="**Live**", 
        inline=False
    )
    embed.add_field(
        name="Title", 
        value=title, 
        inline=True
    )
    embed.add_field(
        name="Game", 
        value=game, 
        inline=True
    )
    embed.add_field(
        name="Live viewers", 
        value=live_views, 
        inline=False
    )
    embed.add_field(
        name="Total views", 
        value=view_count, 
        inline=False
    )
    embed.add_field(
        name="Followers", 
        value=follow_count, 
        inline=False
    )
    embed.add_field(
        name="Subscribers", 
        value=sub_count-1, 
        inline=False
    )

    return embed


class TwitchAPI(commands.Cog, name='Twitch API'):
    """There is a number of functionality that makes use of the Twitch API. The bot monitors when a GameGrammar stream goes live and will automatically post a message in the appropriate channel. You can also get some staticsts of the Twitch channel by using the Twitch stats command. This will include things like Follower count, Subscriber count, latest VOD and, if the stream is currently live, viewer count."""
    is_live = False
    
    para = {
        'Client-id': bot_db.server_get()['twitch']['client_id'],
        'Authorization': bot_db.server_get()['twitch']['oauth2'],
    }

    def __init__(self, bot):
        self.bot = bot
        is_live = False
        went_live_at = bot_db.server_get()
        if 'last_live' not in went_live_at['twitch'].keys():
            bot_db.server_update('update', new_value={'twitch.last_live': datetime.utcnow()})
        self.message = None
        self.twitch_status.start()


    def refresh_token(self):
        refresh_data = requests.get(f'https://twitchtokengenerator.com/api/refresh/{bot_db.server_get()["twitch"]["refresh"]}')

        return refresh_data.text


    def get_live_data(self):
        live_data = requests.get(f'https://api.twitch.tv/helix/streams?user_id={bot_db.server_get()["twitch"]["channel_id"]}', headers=self.para)

        return live_data.text


    def get_broadcaster_data(self):
        broadcaster_data = requests.get(f'https://api.twitch.tv/helix/channels?broadcaster_id={bot_db.server_get()["twitch"]["channel_id"]}', headers=self.para)

        return broadcaster_data.text


    def get_user_info(self):
        user_data = requests.get(f'https://api.twitch.tv/helix/users?id={bot_db.server_get()["twitch"]["channel_id"]}', headers=self.para)

        return user_data.text


    def get_videos(self):
        videos = requests.get(f'https://api.twitch.tv/helix/videos?user_id={bot_db.server_get()["twitch"]["channel_id"]}', headers=self.para)

        return videos.text


    def get_follows(self):
        follows = requests.get(f'https://api.twitch.tv/helix/users/follows?to_id={bot_db.server_get()["twitch"]["channel_id"]}', headers=self.para)

        return follows.text


    def get_subs(self):
        subs = json.loads(requests.get(f'https://api.twitch.tv/helix/subscriptions?broadcaster_id={bot_db.server_get()["twitch"]["channel_id"]}', headers=self.para).text)
        
        next_subs = subs

        cursor = subs['pagination']['cursor']

        while bool(next_subs['pagination']):
            cursor = next_subs['pagination']['cursor']
            next_subs = json.loads(requests.get(f'https://api.twitch.tv/helix/subscriptions?broadcaster_id={bot_db.server_get()["twitch"]["channel_id"]}&after={cursor}', headers=self.para).text)
            subs['data'].extend(next_subs['data'])

        return subs


    def get_game(self, game_id):
        game_data = requests.get(f'https://api.twitch.tv/helix/games?id={game_id}', headers=self.para)

        return game_data.text


    # check if at least six hours have passed
    def six_h_passed(self):
        return datetime.utcnow() - bot_db.server_get()['twitch']['last_live'] > timedelta(hours=6)


    @commands.command(
        name='twitch_stats', 
        aliases=['ts'], 
        brief='Shows statistics of the GameGrammar Twitch channel.',
        help='With this command you can at any point see information about the GameGrammar Twitch channel. Especially useful if you want a quick link to the channel or the lastes VOD.',
        usage='Usage: `!twitch_stats\!ts`')
    @commands.guild_only()
    async def twitch_stats(self, ctx):
        data = json.loads(self.get_live_data())
        
        # if stream online
        if len(data['data']) > 0:
            game_data = json.loads(self.get_game(data['data'][0]['game_id']))
            follows = json.loads(self.get_follows())
            subs = self.get_subs()
            user_info = json.loads(self.get_user_info())

            title = data['data'][0]['title']
            game_name = ''
            try:
                game_name = game_data['data'][0]['name']
            except:
                game_name = 'None'
            viewer_count = data['data'][0]['viewer_count']
            follow_count = follows['total']
            sub_count = len(subs['data'])
            view_count = user_info['data'][0]['view_count']
            thumb_url = data['data'][0]['thumbnail_url'].replace('{width}', '1280').replace('{height}', '720')

            await ctx.send(
                embed=create_live_embed(
                    ctx.author,
                    title,
                    game_name,
                    viewer_count,
                    follow_count,
                    sub_count,
                    view_count,
                    thumb_url
                )
            )
    
        # if stream offline
        else:
            broadcaster_data = json.loads(self.get_broadcaster_data())
            game_data = json.loads(self.get_game(broadcaster_data['data'][0]['game_id']))
            follows = json.loads(self.get_follows())
            subs = self.get_subs()
            user_info = json.loads(self.get_user_info())
            latest_video = json.loads(self.get_videos())

            title = broadcaster_data['data'][0]['title']
            game_name = ''
            try:
                game_name = game_data['data'][0]['name']
            except:
                game_name = 'None'

            follower_count = follows['total']
            sub_count = len(subs['data'])
            view_count = user_info['data'][0]['view_count']
            latest_video_title = latest_video['data'][0]['title']
            latest_video_url = latest_video['data'][0]['url']

            await ctx.send(
                embed=create_offline_embed(
                    ctx.author,
                    title,
                    game_name,
                    follower_count,
                    sub_count,
                    view_count,
                    latest_video_title,
                    latest_video_url
                )
            )


    def cog_unload(self):
        self.twitch_status.cancel()


    @tasks.loop(seconds=60)
    async def twitch_status(self):
        data = json.loads(self.get_live_data())
        try:
            # if stream online
            guild = discord.utils.get(self.bot.guilds, name=bot_db.server_get()["guild_name"])
            channel = discord.utils.get(guild.channels, id=bot_db.server_get()["stream_channel_id"])
            if len(data['data']) > 0 and not self.is_live and self.six_h_passed():
                game = json.loads(self.get_game(data['data'][0]['game_id']))
                title = data['data'][0]['title']
                thumb_url =  data['data'][0]['thumbnail_url'].replace('{width}', '1280').replace('{height}', '720')
                game_name = ''
                try:
                    game_name = game['data'][0]['name']
                except:
                    game_name = 'None'
                viewer_count = data['data'][0]['viewer_count']

                self.message = await channel.send(
                    content='Hey <@&739058472704016487> , GameGrammar has gone live!', 
                    embed=create_notif_embed(
                        title,
                        thumb_url,
                        game_name,
                        viewer_count
                    )
                )
                bot_db.server_update('update', new_value={'twitch.live_at': datetime.utcnow()})
                self.is_live = True
                print('Stream went live')
            elif len(data['data']) == 0 and self.is_live:
                self.is_live = False
                print('Not live anymore!')
            elif len(data['data']) > 0 and self.is_live:
                game = json.loads(self.get_game(data['data'][0]['game_id']))
                title = data['data'][0]['title']
                thumb_url =  data['data'][0]['thumbnail_url'].replace('{width}', '1280').replace('{height}', '720')
                game_name = ''
                try:
                    game_name = game['data'][0]['name']
                except:
                    game_name = 'None'
                viewer_count = data['data'][0]['viewer_count']

                await self.message.edit( 
                    content='Hey <@&739058472704016487> , GameGrammar has gone live!', 
                    embed=create_notif_embed(
                        title,
                        thumb_url,
                        game_name,
                        viewer_count
                    )
                )
        except Exception as e:
            print('Error while trying to post live ping!', e)
            pass

        refreshtime = bot_db.server_get()['twitch']['refreshtime']
        now = datetime.utcnow()

        if now > refreshtime:
            refresh_data = json.loads(self.refresh_token())

            if refresh_data['success']:
                bot_db.server_update('update', new_value={'twitch.oauth2': f'Bearer {refresh_data["token"]}'})
                refreshtime = now + timedelta(days=30)
                bot_db.server_update('update', new_value={'twitch.refreshtime': refreshtime})
                print('oauth token refreshed')
            else:
                print('Error while trying to refresh oauth token')



def setup(bot):
    bot.add_cog(TwitchAPI(bot))