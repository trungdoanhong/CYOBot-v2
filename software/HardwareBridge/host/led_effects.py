"""33-pixel PCB matrix + 12-pixel clockwise ring; pure frame generation."""
import colorsys
import math

CHARACTER_PIXELS=(0,1,2,3,4,6,7,8,9,10,14,15,16,17,18,22,23,24,25,26,28,29,30,31,32)
# Five rows, five columns; extra edge LEDs remain off for readable text.
FONT={
'A':['01110','10001','11111','10001','10001'],'B':['11110','10001','11110','10001','11110'],
'C':['01111','10000','10000','10000','01111'],'D':['11110','10001','10001','10001','11110'],
'E':['11111','10000','11110','10000','11111'],'F':['11111','10000','11110','10000','10000'],
'G':['01111','10000','10111','10001','01111'],'H':['10001','10001','11111','10001','10001'],
'I':['11111','00100','00100','00100','11111'],'J':['00111','00010','00010','10010','01100'],
'K':['10001','10010','11100','10010','10001'],'L':['10000','10000','10000','10000','11111'],
'M':['10001','11011','10101','10001','10001'],'N':['10001','11001','10101','10011','10001'],
'O':['01110','10001','10001','10001','01110'],'P':['11110','10001','11110','10000','10000'],
'Q':['01110','10001','10101','10010','01101'],'R':['11110','10001','11110','10010','10001'],
'S':['01111','10000','01110','00001','11110'],'T':['11111','00100','00100','00100','00100'],
'U':['10001','10001','10001','10001','01110'],'V':['10001','10001','10001','01010','00100'],
'W':['10001','10001','10101','11011','10001'],'X':['10001','01010','00100','01010','10001'],
'Y':['10001','01010','00100','00100','00100'],'Z':['11111','00010','00100','01000','11111'],
'0':['01110','10011','10101','11001','01110'],'1':['00100','01100','00100','00100','01110'],
'2':['11110','00001','01110','10000','11111'],'3':['11110','00001','01110','00001','11110'],
'4':['10010','10010','11111','00010','00010'],'5':['11111','10000','11110','00001','11110'],
'6':['01111','10000','11110','10001','01110'],'7':['11111','00001','00010','00100','00100'],
'8':['01110','10001','01110','10001','01110'],'9':['01110','10001','01111','00001','11110'],
' ':['00000']*5,'!':['00100','00100','00100','00000','00100'],
'?':['01110','00001','00110','00000','00100'],'-':['00000','00000','11111','00000','00000'],
'.':['00000','00000','00000','00000','00100']}
ICONS={'heart':['01010','11111','11111','01110','00100'],
       'smile':['00000','01010','00000','10001','01110'],
       'wink':['00000','01011','00000','10001','01110']}

class LedEffect:
    def __init__(self, effect='text', text='HELLO', color=(83,217,155), brightness=20, speed=1):
        if not isinstance(effect,str) or effect not in ('text','heartbeat','face','rainbow','chase'):
            raise ValueError('Unknown LED effect')
        if effect!='text':text='HELLO'
        if not isinstance(text,str) or not 1<=len(text)<=32 or any(c not in FONT for c in text.upper()):
            raise ValueError('Text: 1–32 characters, A–Z, 0–9, space, ! ? - .')
        if not isinstance(color,(tuple,list)) or len(color)!=3 or any(type(c)is not int or not 0<=c<=255 for c in color):
            raise ValueError('Color must contain three RGB bytes')
        if type(brightness) not in (int,float) or not math.isfinite(brightness) or not 0<=brightness<=100:
            raise ValueError('Brightness must be 0–100')
        if type(speed) not in (int,float) or not math.isfinite(speed) or not .5<=speed<=2:
            raise ValueError('LED speed must be 0.5–2')
        self.effect,self.text,self.color,self.brightness,self.speed=effect,text.upper(),color,brightness,speed
        self.columns=[(0,)*5]*5
        for char in self.text:
            rows=FONT[char]
            self.columns.extend(tuple(int(rows[y][x]) for y in range(5)) for x in range(5))
            self.columns.append((0,)*5)
        self.columns += [(0,)*5]*5
        self.steps=len(self.columns)-4 if effect=='text' else 32 if effect in ('face','heartbeat') else 24
        self.interval=.125/speed

    def frame(self, index):
        index=int(index)%self.steps
        matrix=[[0,0,0] for _ in range(33)];ring=[[0,0,0] for _ in range(12)]
        def rgb(color=self.color,level=1):return [round(c*self.brightness/100*level) for c in color]
        def glyph(rows,level=1):
            for y,row in enumerate(rows):
                for x,on in enumerate(row):
                    if on=='1':matrix[CHARACTER_PIXELS[y*5+x]]=rgb(level=level)
        if self.effect=='text':
            for x in range(5):
                for y,on in enumerate(self.columns[index+x]):
                    if on:matrix[CHARACTER_PIXELS[y*5+x]]=rgb()
            ring[(index//2)%12]=rgb()
        elif self.effect=='heartbeat':
            level=.15+.85*((1+math.cos(index*math.tau/16))/2)**3
            glyph(ICONS['heart'],level);ring=[rgb(level=level) for _ in ring]
        elif self.effect=='face':
            glyph(ICONS['wink' if index>=27 else 'smile']);ring=[rgb(level=.25) for _ in ring]
        elif self.effect=='rainbow':
            for group in (matrix,ring):
                for i in range(len(group)):group[i]=rgb([round(c*255) for c in colorsys.hsv_to_rgb((i/len(group)+index/24)%1,1,1)])
        else:
            glyph(ICONS['smile'])
            for tail in range(4):ring[(index//2-tail)%12]=rgb(level=(4-tail)/4)
        return dict(matrix=matrix,ring=ring)

    def preview(self):
        return dict(interval=self.interval,frames=[self.frame(i) for i in range(self.steps)])
