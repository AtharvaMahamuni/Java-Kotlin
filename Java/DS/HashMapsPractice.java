package DS;

import java.util.HashMap;

public class HashMapsPractice {

    public static void main(String[] args) {

        int a = 10;
        int b = 20;
        int c = 30;

        HashMap<String, Integer> happy = new HashMap<String, Integer>();

        happy.put("a", 10);
        happy.put("b", 20);
        happy.put("c", 30);

        System.out.println(happy);

        System.out.println(happy.containsKey("a"));
        System.out.println(happy.containsValue(20));
        
        System.out.println(happy.get("a"));

    }

}
